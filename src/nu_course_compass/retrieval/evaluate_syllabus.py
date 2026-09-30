"""Private, local diagnostic comparing strict, OR lexical and dense ranking.

This is an experiment, not the production retriever. Inputs and output contain
restricted provenance and must stay under ignored data/. No remote inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def metrics(expected: set[str], ranked: list[str]) -> dict:
    if not expected:
        return {"returned_candidates": len(ranked)}
    hits = expected.intersection(ranked)
    first = next((i for i, value in enumerate(ranked, 1) if value in expected), None)
    return {"recall_at_5": len(hits) / len(expected),
            "reciprocal_rank_at_5": 1 / first if first else 0,
            "hit_at_5": int(bool(hits))}


def windows(tokens: list[int], budget: int = 254, overlap: int = 32) -> list[list[int]]:
    if budget <= overlap or overlap < 0:
        raise ValueError("window budget must exceed nonnegative overlap")
    if not tokens:
        raise ValueError("cannot embed empty text")
    result = []
    start = 0
    while start < len(tokens):
        result.append(tokens[start:start + budget])
        if start + budget >= len(tokens):
            break
        start += budget - overlap
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", type=Path)
    parser.add_argument("--model", type=Path, required=True,
                        help="Already downloaded pinned local MiniLM model directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from nu_course_compass.persistence.connection import get_db_connection
    import torch
    import transformers
    from transformers import AutoModel, AutoTokenizer

    question_bytes = args.questions.read_bytes()
    config = json.loads(question_bytes)
    with get_db_connection() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        rows = conn.execute("SELECT chunk_id, content, metadata FROM syllabus_chunks ORDER BY chunk_id").fetchall()
        corpus = [{"chunk_id": row[0], "content": row[1], "metadata": row[2]} for row in rows]
        if not corpus:
            raise ValueError("empty corpus")
        questions = []
        for item in config["questions"]:
            expected = {r["chunk_id"] for r in corpus
                        if r["metadata"].get("course_code") == config["course_code"]
                        and r["metadata"].get("semester") == config["semester"]
                        and r["metadata"].get("page") in item["expected_pages"]}
            pages = {r["metadata"].get("page") for r in corpus if r["chunk_id"] in expected}
            if pages != set(item["expected_pages"]):
                raise ValueError(f"Missing expected evidence for {item['id']}")
            record = {**item, "expected_chunk_ids": sorted(expected), "results": {}}
            for method in ("strict", "permissive"):
                # OR is constructed from server-normalized lexemes, not raw SQL.
                query = "websearch_to_tsquery('english', %s)" if method == "strict" else """
                  to_tsquery('english', coalesce((SELECT string_agg(quote_literal(term), ' | ')
                    FROM unnest(tsvector_to_array(to_tsvector('english', %s))) AS term), ''))
                """
                sql = f"""WITH q AS (SELECT {query} AS value)
                  SELECT chunk_id FROM syllabus_chunks CROSS JOIN q
                  WHERE numnode(q.value)>0 AND search_vector @@ q.value
                    AND metadata->>'course_code'=%s AND metadata->>'semester'=%s
                  ORDER BY ts_rank_cd(search_vector,q.value) DESC,chunk_id LIMIT 5"""
                ranked = [r[0] for r in conn.execute(sql, (item["question"], config["course_code"], config["semester"])).fetchall()]
                record["results"][method] = {"chunk_ids": ranked, **metrics(expected, ranked)}
            questions.append(record)

    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = AutoModel.from_pretrained(args.model, local_files_only=True, use_safetensors=True).eval()

    def embed(texts):
        sequences = [[tokenizer.cls_token_id, *t, tokenizer.sep_token_id] for t in texts]
        length = max(map(len, sequences))
        encoded = {
            "input_ids": torch.tensor([s + [tokenizer.pad_token_id] * (length-len(s)) for s in sequences]),
            "attention_mask": torch.tensor([[1] * len(s) + [0] * (length-len(s)) for s in sequences]),
        }
        with torch.inference_mode():
            hidden = model(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1)
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
            return torch.nn.functional.normalize(pooled, p=2, dim=1)

    all_windows, owners = [], []
    for index, row in enumerate(corpus):
        for window in windows(tokenizer.encode(row["content"], add_special_tokens=False, verbose=False)):
            all_windows.append(window)
            owners.append(index)
    vectors = torch.cat([embed(all_windows[i:i + 8]) for i in range(0, len(all_windows), 8)])
    for record in questions:
        tokens = tokenizer.encode(record["question"], add_special_tokens=False)
        if len(tokens) > 254:
            raise ValueError("question exceeds model budget")
        scores = (vectors @ embed([tokens])[0]).tolist()
        chunk_scores = {}
        for owner, score in zip(owners, scores):
            row = corpus[owner]
            if row["metadata"].get("course_code") == config["course_code"] and row["metadata"].get("semester") == config["semester"]:
                key = row["chunk_id"]
                chunk_scores[key] = max(score, chunk_scores.get(key, -float("inf")))
        ranked = sorted(chunk_scores, key=lambda key: (-chunk_scores[key], key))[:5]
        record["results"]["dense"] = {"chunk_ids": ranked,
            "scores": [chunk_scores[key] for key in ranked],
            **metrics(set(record["expected_chunk_ids"]), ranked)}

    summary = {}
    answerable = [q for q in questions if q["expected_chunk_ids"]]
    for method in ("strict", "permissive", "dense"):
        summary[method] = {name: sum(q["results"][method][name] for q in answerable) / len(answerable)
                          for name in ("recall_at_5", "reciprocal_rank_at_5", "hit_at_5")}
        summary[method]["unanswerable_candidate_counts"] = {
            q["id"]: len(q["results"][method]["chunk_ids"])
            for q in questions if not q["expected_chunk_ids"]}
    report = {"scope": config["scope"], "review_status": config["review_status"],
              "corpus_sha256": hashlib.sha256(json.dumps(corpus, sort_keys=True).encode()).hexdigest(),
              "question_sha256": hashlib.sha256(question_bytes).hexdigest(),
              "corpus_chunks": len(corpus), "frozen_corpus": corpus,
              "model": str(args.model),
              "model_weights_sha256": hashlib.file_digest((args.model / "model.safetensors").open("rb"), "sha256").hexdigest(),
              "versions": {"torch": torch.__version__, "transformers": transformers.__version__},
              "dense_settings": {"content_tokens": 254, "overlap": 32, "pooling": "masked mean; L2 normalized", "chunk_score": "max window cosine", "device": "cpu"},
              "summary": summary, "questions": questions}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Never silently replace an earlier experiment.
    with args.output.open("x") as output:
        json.dump(report, output, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
