"""Rank historical syllabus chunks with PostgreSQL full-text search."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from langchain_core.documents import Document
import psycopg


@dataclass(frozen=True)
class SearchResult:
    document: Document
    score: float
    excerpt: str


def search(
    question: str,
    *,
    course_code: str | None = None,
    semester: str | None = None,
    limit: int = 5,
    connection: psycopg.Connection | None = None,
) -> list[SearchResult]:
    """Return ranked evidence, not generated answers or current offerings.

    An injected connection remains caller-owned. Otherwise a short-lived
    connection is opened and closed for this lookup.
    """
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    if not isinstance(question, str):
        raise ValueError("question must be text")
    if not question.strip():
        return []
    if connection is None:
        from nu_course_compass.persistence.connection import get_db_connection

        with get_db_connection() as conn:
            return search(question, course_code=course_code, semester=semester,
                          limit=limit, connection=conn)

    conditions = ["numnode(query.value) > 0", "chunks.search_vector @@ query.value"]
    parameters: list[object] = [question, "MaxWords=45, MinWords=15, StartSel=<<, StopSel=>>"]
    for field, value in (("course_code", course_code), ("semester", semester)):
        if value is not None:
            # Field names are fixed above, never supplied by the user.
            conditions.append(f"chunks.metadata->>'{field}' = %s")
            parameters.append(value)
    parameters.append(limit)
    statement = """
        WITH query AS (SELECT websearch_to_tsquery('english', %s) AS value)
        SELECT chunks.chunk_id, chunks.content, chunks.metadata,
               ts_rank_cd(chunks.search_vector, query.value) AS score,
               ts_headline('english', chunks.content, query.value, %s) AS excerpt
        FROM syllabus_chunks AS chunks CROSS JOIN query
        WHERE """ + " AND ".join(conditions) + " ORDER BY score DESC, chunks.chunk_id ASC LIMIT %s"
    rows = connection.execute(statement, parameters).fetchall()
    return [SearchResult(Document(id=chunk_id, page_content=content, metadata=metadata),
                         float(score), excerpt)
            for chunk_id, content, metadata, score, excerpt in rows]


def format_result(result: SearchResult, rank: int) -> str:
    metadata = result.document.metadata
    if "page" in metadata:
        location = f"page {metadata['page']}"
    else:
        location = f"blocks {metadata['block_start']}–{metadata['block_end']}"
    return (
        f"{rank}. {metadata['course_code']} | {metadata['semester']} | "
        f"{location} | score={result.score:.6f}\n"
        f"{result.excerpt}\n"
        f"Source: {metadata['source_url']}\n"
        f"Retrieved: {metadata['retrieved_at']}\n"
        f"Chunk: {result.document.id}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--course-code")
    parser.add_argument("--semester")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    results = search(args.question, course_code=args.course_code,
                     semester=args.semester, limit=args.limit)
    print("Historical syllabus evidence only; not current offerings or eligibility advice.")
    if not results:
        print("No matching syllabus evidence.")
    for rank, result in enumerate(results, start=1):
        print(format_result(result, rank))
        print()


if __name__ == "__main__":
    main()
