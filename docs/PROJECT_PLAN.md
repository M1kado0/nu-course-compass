# NU Course Compass — local chatbot plan

**Status:** implementation plan, updated 2026-09-29
**Product contract:** [AGENTS.md](../AGENTS.md)

## Outcome and decisions

Build toward an independent, English-first web chatbot for NU courses, academic rules/programs, and selected student services. **The immediate deliverable is a private, local syllabus-ingestion and retrieval pilot**, not a public chatbot and not a current-term schedule assistant. The later local chat demo uses Streamlit, FastAPI, and PostgreSQL; an exact Registrar lookup must sit behind chat before the assistant can answer offering questions. The application must remain useful with the model switched off.

Use LangChain `Document`/loader/Runnable interfaces for unstructured content and grounded generation. Start retrieval with PostgreSQL full-text search; test local embeddings and pgvector/RRF hybrid search against a frozen NU question set before enabling hybrid by default. Use no agentic RAG or LangGraph in v1. NUSpace is an attributed [link](https://nuspace.kz/courses/?tab=course-stats), not an ingested source, because its [terms disallow scraping without prior consent](https://nuspace.kz/terms-of-service).

This plan replaces the former multi-page explorer, prerequisite graph, 300-query training benchmark, custom model training, GPU serving, and Azure-first delivery commitments. Those are not required to declare the local chatbot complete.

## Verified starting point and source audit

- The existing package is `src/nu_course_compass/`. `ingestion/download_registrar.py` fetches the Fall 2026 schedule as **legacy XLS**, and `parse_schedule_xls.py` parses its 15-column sheet with `xlrd`, retaining original cells and spreadsheet row numbers. That path is retained but deferred. The MOE pilot adds a separate sheet importer, local PDF/DOCX snapshots, citation-bearing LangChain documents, and a lexical retrieval baseline. No API, chat UI, database schema, or generated-answer service is present yet.
- The [MOE Syllabi Database](https://docs.google.com/spreadsheets/d/1R9a86iwqr7oDo60hZt6WQLPm0EDRXNTu5-r7vt0IKgU/edit) has eleven semester tabs from Fall 2022 through Summer 2026. It is view-only and available to NU accounts, not anonymous public access. Rows include course code, instructor, semester, and links that may target PDF files, Google Docs/Slides, or folders. This is a student-government index, not an official Registrar offering feed; every syllabus must retain its own URL and historical term.
- [Registrar schedules](https://registrar.nu.edu.kz/course-schedules) provide XLS/PDF term files; [requirements](https://registrar.nu.edu.kz/course-requirements) provide term/school requirement documents. Use the XLS for row facts and the PDF as a layout cross-check. Requirements need separate extraction and verification.
- [Registrar resources](https://registrar.nu.edu.kz/quick-links/resources) mixes current guidance with old workshops/orientations. Allowlist individual relevant pages with their dates; do not index the entire resources page as current policy.
- The [Public Course Catalog](https://registrar.nu.edu.kz/course-catalog) has a dynamic search interface; the inspected static page exposed filters but no course rows. Validate a permitted, reproducible extraction method and sample descriptions before claiming catalog coverage. If extraction fails, cite available Registrar records and say descriptions are unavailable.
- `nu.edu.kz` spans many unrelated sections. The first allowlist should take relevant English pages from [academics](https://nu.edu.kz/academics/) and [student information](https://nu.edu.kz/students/)—for example academic services, important documents, and support/rights—plus linked authoritative documents. Exclude news, research, admissions, and events until separately scoped.
- Start from manually reviewed local snapshots and fixtures. Check automation rules or obtain permission before unattended Registrar/NU crawling. Never scrape NUSpace or use its undocumented endpoints.

## Delivery gates

### 0. Private local syllabus pilot — current milestone

1. Create a Google Desktop OAuth client and run the read-only MOE importer with a local client-secret JSON. Browser login alone does not authenticate the Python process. The default run is capped at ten rows; use repeated `--row gid:row` selections to deliberately sample file types and terms. If the NU domain blocks the API or a file disallows downloading, record the result and stop for that source—do not reuse browser cookies or bypass controls.
2. Read the eleven known tab IDs, repeated school/header blocks, and syllabus hyperlinks. Record index tab/gid/row, course code, instructor, semester, school, URL, retrieval time, Drive MIME type, modified time, status, and reason. Download supported PDFs and DOCX files in their original format, or PDF exports of Google Docs/Slides. Store immutable checksum-named snapshots in ignored `data/raw/moe_syllabi/`; re-importing an unchanged file must not duplicate it. Skip folders, inaccessible files, and unsupported URLs.
3. Load local PDF snapshots page-by-page with LangChain `PyMuPDFLoader`; parse native DOCX paragraphs and unique table cells in order with `python-docx`. Pack whole paragraph/table-row blocks up to the chunk budget, splitting only an oversized block. Write deterministic citation-bearing LangChain chunks to ignored `data/processed/`, retaining PDF page locations or DOCX block ranges (not fabricated DOCX page numbers). Preserve the original syllabus and index URLs, historical semester, and checksum. Run the model-free lexical search on a small manually reviewed question set. Historical syllabi cannot establish current offerings or personal eligibility.
4. After the ten-link trial, inspect downloaded-file counts, parser quality, citation locations, missing files, and duplicate behavior. Expand beyond the pilot only after this check. Keep the corpus and OAuth credentials local; publication/access is a separate decision.

**Run locally:**

```bash
uv run python -m nu_course_compass.ingestion.import_moe_syllabi --client-secret data/raw/google-client-secret.json --inventory --limit 50
uv run python -m nu_course_compass.ingestion.import_moe_syllabi --client-secret data/raw/google-client-secret.json --row 'GID:ROW' --row 'GID:ROW'
uv run python -m nu_course_compass.ingestion.load_syllabus_documents data/raw/moe_syllabi/manifest.jsonl
uv run python -m nu_course_compass.retrieval.syllabus_search data/processed/moe_syllabi_chunks.jsonl "Which syllabus covers transformers?"
uv run pytest -q tests/ingestion
```

Choose actual `gid:row` values from the inventory output; use no more than ten for the initial manual pilot. Once offline tests cover explicit all-rows selection, transient-error retries, and checkpointed batching, try a bounded 20–50-row import (for example, `--limit 25 --batch-size 10`). Review downloaded, reused, skipped, failed, and sheet-issue counts before any larger run. `--all-rows` explicitly attempts every parsed index row; it cannot be combined with `--limit` and does not guarantee every syllabus is accessible or supported. Do not commit the client-secret JSON, OAuth token, downloaded PDFs, manifest, or extracted chunks. The importer requests read-only Sheets/Drive OAuth access; NU administrators may need to allow that client. `--limit` defaults to ten and never exceeds one hundred per invocation when `--all-rows` is absent.

**Exit:** At least ten deliberately selected links have recorded outcomes; accessible documents are parsed and cited accurately; reruns do not duplicate unchanged snapshots or chunks; a short reviewed question set identifies both relevant evidence and unsupported current-offering questions. Live access and corpus coverage remain unverified until the user runs OAuth import.

### 1. Reproducible official-source ingestion — later

1. After the syllabus pilot, inventory a small official-source allowlist: one current schedule XLS and matching PDF; one requirements PDF; a few catalog records if extractable; and roughly 10–20 relevant NU/Registrar guidance pages or linked documents. Record why each source is included, its official URL, retrieval date, and effective term/date. Do not represent the syllabus pilot as complete NU coverage.
2. Make snapshot acquisition explicit and repeatable without overwriting earlier bytes. Validate file signature, SHA-256, format, parser version, and import results. Keep raw files ignored and add small sanitized fixtures for tests. The existing downloader needs snapshot-safe output naming before it is used repeatedly.
3. Reuse `parse_schedule_xls` for the legacy workbook; compare 10–20 representative rows with the official PDF, including multi-day meetings and odd sections. Normalize course and offering keys without discarding original row values.
4. Add a separate requirements/PDF path using a suitable LangChain loader only when it preserves page metadata. Store source text verbatim and the page/record citation. Do not claim a machine-readable Boolean prerequisite expression until a deterministic parser is tested; ambiguous requirements are quoted with a limitation.
5. For HTML, remove navigation/boilerplate and retain section headings. Split by heading/section first; only oversized sections use a token-aware recursive splitter, initially targeting about 600 tokens with 80-token overlap. Never split a schedule row or short course description merely to meet that target. Compare chunk boundaries on representative course, policy, and service questions before freezing settings.

**Exit:** An offline fixture can be imported twice without duplicates, queried by course code, and traced back to exact source URL, snapshot, row/page, and retrieval date. Catalog and NU page coverage is documented honestly.

### 2. Cited chat with lexical retrieval

1. Add reviewed PostgreSQL migrations for snapshots, course/offering records, and source text chunks with stable IDs and provenance. Add a full-text index over approved chunks. Use the existing Python package for ingestion/domain/retrieval/RAG modules; do not create a parallel backend package.
2. Add FastAPI `POST /v1/ask` with typed question and optional term filter; return answer, citations, limitations, freshness, and trace ID. Add live/ready health endpoints. The exact-code/term path queries validated Registrar rows before generation. For requirements, quote the published text rather than guessing its logic.
3. Build a LangChain two-step Runnable: retrieve evidence, then generate once from the original question and bounded evidence. Verify output citation IDs against retrieved records and preserve deterministic course facts. If evidence is absent, citations fail, or the model is unavailable, return cited lookup/search evidence or an explicit no-answer response.
4. Build one Streamlit chat screen with sources, effective dates, limitations, model-off state, and an independent-project disclaimer. Use one typed HTTP client; keep credentials, SQL, and prompts in the backend. Do not persist conversation transcripts by default.

**Exit:** A local user can ask about an exact offering and a student-service topic and receive source-linked responses. The exact offering and cited search path still work with no model key. Tests run with a fake model and no live NU website.

### 3. Evaluate retrieval, then decide on hybrid

1. Create a manually reviewed set of at least 60 questions spanning exact courses/terms, topical course discovery, academic/student-service information, and conflicting or unanswerable cases. Store expected source IDs and prohibited claims. Keep a held-out subset untouched until selection is frozen.
2. Record full-text Recall@5, MRR, exact-code correctness, and no-answer behavior. Then add a pinned local embedding model and the maintained LangChain `PGVectorStore` in the same PostgreSQL service. Compare vector-only and RRF-fused hybrid results on the same chunks and filters.
3. Enable hybrid by default only if it improves retrieval on topical/policy questions without regressing exact-code or no-answer behavior; otherwise retain lexical search and publish the comparison. Do not add a reranker, query rewriting, or trained retriever without a new measured need.
4. Evaluate final answers separately for citation validity, factual support, current-versus-historical wording, unsupported eligibility claims, and model-off fallback. A citation ID existing in retrieved evidence is necessary but does not by itself prove the answer is supported.

**Exit:** The selected retriever has a reproducible comparison report, and the chatbot passes reviewed answer examples without invented courses, instructors, or prerequisites.

### 4. Finish the local demo

Document setup, source inventory, data limitations, selected model and embedding revisions, and exact local run/test commands in the README. Use `uv` and the committed lock file; add only dependencies used by the selected path and remove unused prototype dependencies after checking imports. Run unit/integration and Streamlit smoke tests, inspect the working-tree diff, and report observed results. Azure deployment and a broader crawler require separate access, cost, and quality decisions.

**Exit:** A clean checkout can reproduce the local demo from approved/sanitized fixtures, with no Registrar, NUSpace, Azure, or live model dependency in automated tests.

## References and revisit triggers

[CIA](https://github.com/4-han/CIA) demonstrates a campus chatbot with source links, retrieval evaluation, and feedback, but its Telegram/Minsearch stack is not a template for Registrar course facts. [LLM Zoomcamp's project guide](https://github.com/DataTalksClub/llm-zoomcamp/blob/main/project.md) motivates comparing retrieval alternatives and evaluating answers, not adopting agents by default. [pgvector](https://github.com/pgvector/pgvector) and [LangChain Postgres](https://github.com/langchain-ai/langchain-postgres) document the proposed one-database hybrid option. Revisit this plan if source access rules change, catalog extraction proves infeasible, the source allowlist expands, or evaluation demonstrates a need for more complex retrieval.
