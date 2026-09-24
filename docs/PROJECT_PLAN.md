# NU Course Compass: Step-by-Step Project Plan

**Status:** implementation roadmap  
**Plan date:** 2026-09-25  
**Scope authority:** [`AGENTS.md`](../AGENTS.md)

This roadmap translates the product contract in `AGENTS.md` into an ordered set of implementation steps, exit gates, and validation work. The plan follows the stated delivery order and keeps deterministic course information useful before any LLM feature is introduced.

## Evidence and planning basis

| Source | What was checked | Planning implication | Confidence |
|---|---|---|---|
| Local [`AGENTS.md`](../AGENTS.md) | Product rules, target architecture, source policy, acceptance requirements, budget, and delivery order | Treat this file as the product contract; do not start a later capability before its correctness gate passes | Verified |
| Local [`pyproject.toml`](../pyproject.toml), [`README.md`](../README.md), and [`src/nu_course_compass/__init__.py`](../src/nu_course_compass/__init__.py) | Current project is a minimal Python package with a placeholder `main()`; README has no project content; target API, UI, ingestion, graph, and tests are not present | Begin with repository alignment and a small source-to-API vertical slice; do not assume the target system already exists | Verified |
| Local root files and test/config files | No Makefile, tests, backend/UI folders, migration setup, or container configuration are present | Establish runnable local commands and CI as early foundation work | Verified |
| GitHub `M1kado0/nu-course-compass` | Local remote points to this repo; current history contains the initial scaffold; open-issue query returned zero | No existing issue backlog or implementation sequence was available to merge into this roadmap | Verified |
| [BEIR paper](https://arxiv.org/abs/2104.08663) and [BEIR dataset card](https://huggingface.co/datasets/BeIR/beir) | BEIR covers varied information-retrieval tasks and uses corpus, queries, and relevance judgments | Use a small public benchmark for general retrieval smoke checks; it cannot replace NU-specific quality evaluation | Verified |
| [MTEB paper](https://aclanthology.org/2023.eacl-main.148/) | Embedding performance varies by task; no one method dominates every embedding task | Select models by the project’s held-out course benchmark, not a broad leaderboard alone | Verified |
| [Sentence Transformers training guide](https://github.com/huggingface/sentence-transformers/blob/main/examples/sentence_transformer/training/ms_marco/README.md) and [current training overview](https://github.com/huggingface/sentence-transformers/blob/main/docs/migration_guide.md) | Official examples use a bi-encoder, contrastive objectives, relevant pairs/triplets, hard negatives, and evaluation before/after training | Keep frozen retrieval as the baseline; train only after NUCourseBench and negative examples are reviewed | Verified |
| [FastAPI dependency override guide](https://fastapi.tiangolo.com/advanced/testing-dependencies/) | FastAPI supports replacing dependencies for isolated tests | Use explicit provider/database ports or FastAPI dependency overrides in API tests; keep tests independent of live services | Verified |
| [FastAPI/PostgreSQL example](https://github.com/darioblanco/fastapi-example) and [production-RAG course repository](https://github.com/Akshay4452/production-agentic-rag-course) | Read their repository guides for modular routes, migrations, fixtures, containers, staged lexical-to-hybrid retrieval, and observability | Treat these as learning examples only. Their stacks and authentication/agent features are not requirements for this project | Verified as repository contents; not production endorsements |
| Learning-video references requested by the local `AGENTS.md` addendum | The current repository materials do not identify video titles or URLs | Add exact references when available; do not invent course or video citations | Not checked |
| [NVIDIA agent-skill catalog](https://github.com/NVIDIA/skills) | The catalog lists `rag-eval`, `rag-perf`, and `rag-blueprint` | They may inform a later optional experiment; they are not required runtime dependencies or a reason to add a persistent GPU service | Verified |
| Hugging Face MCP paper/dataset search | Paper search returned “tool not found”; dataset search was disabled. The public BEIR card exposed its data layout, but sample rows, revisions, and licenses were not independently audited here | Before adopting any external dataset/model, inspect its actual revision, rows, license, and split; keep all such adoption optional | Not fully checked |

## Current starting point

- The repository has a Python package entry point that prints a placeholder greeting. The project’s API, Streamlit interface, ingestion system, database schema, graph, retrieval, and tests remain to be built.
- The target layout and responsibilities are documented in `AGENTS.md`, but no `Makefile`, Docker Compose setup, or test suite currently exists.
- The current working tree already has unrelated edits to `.gitignore`, `pyproject.toml`, and `uv.lock`, plus untracked `graphify-out/` memory artifacts. Preserve and review those separately when implementation begins.
- `.gitignore` currently excludes `AGENTS.md`. Decide whether that file is intentionally local-only or should be versioned with the repository before relying on it as a shared contributor contract.
- The current dependency declaration should be reconciled with the project contract before the first implementation slice. In particular, LangChain and LangGraph are optional experiments under the stated scope, while required app and data-layer dependencies are not yet represented in the starter package.
- The local `AGENTS.md` addendum asks to preserve reviewed video references, but no titles or URLs are recorded in the available project files. Add them when supplied rather than guessing.
- No delivery dates or Azure region are selected. Estimate schedule and deployment cost after the first local vertical slice and current regional pricing check.

## Product and engineering guardrails

1. Registrar records own published course facts, offerings, instructors, requirements, and source provenance.
2. PostgreSQL/domain models own structured facts and graph edges. Lexical and embedding retrieval find relevant descriptions and policy passages. The LLM can explain retrieved evidence but cannot define or override structured facts.
3. The prerequisite graph is constructed from parsed Registrar requirement expressions, validated course references, and deterministic traversal. Graph construction must work with no model provider configured.
4. Every factual assistant answer must cite its sources. Citation failure or unsupported claims trigger a deterministic evidence response.
5. No student eligibility claims, student profiles, account integration, grade-based recommendations, or instructor rankings.
6. Registrar imports begin from local, manually downloaded XLS/PDF files and fixtures. Do not automate crawling before the source’s automation rules are checked or permission is obtained.
7. NUSpace scraping and undocumented production API access remain prohibited. Keep its provider disabled unless written approval or an approved API is available.
8. Keep Streamlit as a thin HTTP presentation client. Keep domain rules out of Streamlit and FastAPI route functions; keep SQL inside persistence modules.
9. Keep local development and tests usable without Registrar, NUSpace, Foundry, Azure, or a live LLM.
10. Respect the $200 Azure ceiling and category allocations in `AGENTS.md`; no persistent GPU endpoint.

## Delivery sequence

The phases below are ordered. A phase is ready to hand off only when its exit gate passes; record any unmet gate as open work instead of moving it downstream.

### Step 0 — Establish a trustworthy project baseline

**Outcome:** contributors can install, run checks, and understand which repository files define the shared contract.

1. Decide whether `AGENTS.md` is local-only or belongs in version control; adjust ignore/tracking policy only after that decision is documented.
2. Review current dirty files before changing package metadata. Reconcile runtime versus optional dependencies with the architecture in `AGENTS.md`; preserve `uv` and the committed lock-file workflow.
3. Replace placeholder project metadata and README content with setup, scope, source constraints, local commands, and independent-project disclaimer.
4. Add the root command interface from `AGENTS.md` incrementally, starting with bootstrap, lint, typecheck, and test. Add CI for the non-cloud verification path.
5. Add the documented target directories only when the first capability needs them; do not generate the full tree as empty scaffolding.

**Exit gate:** clean checkout can install from the lock file and run the initial quality checks; documentation says which checks are actually available; repository policy for `AGENTS.md` is explicit.

### Step 1 — Define source fixtures, provenance, normalization, and validation

**Outcome:** an official local fixture can become validated normalized records without a live network dependency.

1. Define schemas for source snapshots, courses, offerings, instructors, and requirement source text.
2. Define the provenance fields for every imported artifact: source URL, retrieval timestamp, effective term, SHA-256, content type, parser version, import status, and validation results.
3. Add small sanitized fixtures with explicit source metadata. Keep raw production files, secrets, weights, caches, and generated outputs out of Git.
4. Implement normalization for course codes, instructors, terms, credits, and empty or malformed fields.
5. Add validation reports that preserve source records and explain rejected or ambiguous fields.
6. Make import idempotent by source snapshot/checksum; never overwrite a prior snapshot silently.

**TDD tracer bullet:** write one integration test that imports one sanitized schedule fixture and retrieves its normalized offering with provenance. Then add one behavior at a time for duplicate import, malformed rows, and changed-snapshot handling.

**Exit gate:** fixture import is deterministic, repeatable, source-attributed, and testable offline; reimporting the same snapshot creates no duplicates.

### Step 2 — Build the persistence and FastAPI foundation

**Outcome:** a migrated PostgreSQL schema and a small, typed API shell provide clear ownership boundaries.

1. Add SQLAlchemy models and Alembic migrations for the validated catalog and source snapshots.
2. Add persistence/query modules that own SQL, transactions, and database exception translation.
3. Add Pydantic v2 request/response contracts, modular `APIRouter` groups, and a configured app factory/lifespan.
4. Add shared pagination parameters and response metadata for list endpoints.
5. Define a stable error envelope and trace-ID propagation for success and error responses.
6. Add `/health/live` and `/health/ready`; readiness checks required local dependencies without calling model providers.
7. Add test fixtures for migrated temporary PostgreSQL and FastAPI dependency overrides/fakes.

**Exit gate:** migration from an empty database passes; API schema is typed; pagination and error contracts have API-level tests; container smoke check can start the API and return health status.

### Step 3 — Deliver deterministic catalog endpoints

**Outcome:** structured course and offering questions work without an LLM.

1. Implement `GET /v1/courses` with validated search and filters: query, term, school, department, level, credits, instructor, topic, page, and page size. Semantic topic matching is added with the retrieval baseline in Step 7; before then, topic filtering must use deterministic published/indexed fields.
2. Implement course detail, offerings, requirements, source freshness, and statistics-provider-unavailable responses.
3. Enforce deterministic filters before any semantic ranking; exact course-code lookup must not depend on embeddings.
4. Keep route handlers limited to validation and service orchestration. Put search and business rules in domain services.
5. Test pagination boundaries, invalid filters, stable ordering, empty results, unknown course codes, trace IDs, and consistent error responses.

**Exit gate:** catalog answers come from fixture-backed database queries; no model provider is needed; deterministic facts include source citations/provenance.

### Step 4 — Build the typed Streamlit client, explorer, and course details

**Outcome:** students can search, filter, and inspect courses while the LLM is disabled or unavailable.

1. Add one typed Streamlit-to-FastAPI client with timeouts, trace propagation, safe error mapping, GET-only retry rules, and a fake test implementation.
2. Add shared session-state initialization, validated query-parameter parsing, finite response caching, and cache invalidation by active snapshot/version.
3. Build the explorer with filters, pagination, current-versus-historical labels, loading/empty/error/stale states, and shareable URLs.
4. Build course details with description, credits, academic metadata, offerings, instructors, schedule, raw and parsed requirement display, source, retrieval date, and independent-project disclaimer.
5. Display optional statistics-provider unavailability without breaking the course detail page.
6. Add `AppTest` coverage for render, navigation, invalid codes, no results, API timeout, unavailable backend, and restored query parameters.

**Exit gate:** core browse/detail path works against a fake API or local FastAPI service and remains usable with the model provider off; Streamlit contains no SQL, ingestion, retrieval, or provider calls.

### Step 5 — Parse requirements and build the deterministic prerequisite graph

**Outcome:** published prerequisite/corequisite/anti-requisite logic is readable and traversable without model inference.

1. Build requirement expressions for `AllOf`, `AnyOf`, grade thresholds, programs, standing, permissions, and `RawUnparsed` text.
2. Preserve exact source text alongside every parsed expression. Do not guess Boolean grouping when the source is unclear.
3. Resolve references against the catalog, retain unresolved-node warnings, and validate aliases/cross-listed or renamed courses with source evidence.
4. Construct graph edges only from parsed Registrar requirements and validated references; add cycle detection and deterministic depth-limited traversal.
5. Implement prerequisite and unlock queries in the domain service/API.
6. Add property tests for nested logic, equivalent parentheses/whitespace, malformed expressions, unresolved nodes, and stable traversal.
7. Prove with tests that graph building succeeds when no LLM provider is registered or available.

**Exit gate:** parser never silently discards ambiguous input; graph output is reproducible and cited to the requirement source; graph tests need no model or network.

### Step 6 — Add comparison and complete deterministic course exploration

**Outcome:** students can compare two or three courses using published fields.

1. Add comparison selection using temporary session state and shareable `codes` query parameters.
2. Compare descriptions, credits, level, school/department, current/historical offerings, instructors, requirements, topics, and source freshness.
3. Show missing or conflicting data explicitly. Do not produce an unexplained “best course” score.
4. Add graph links and text/tree fallbacks for all graph visualizations.
5. Exercise both AppTest and targeted browser tests for deep links, keyboard access, responsive layout, and graph alternatives.

**Exit gate:** explorer, detail, graph, and compare pages function as a coherent deterministic application without assistant availability.

### Step 7 — Establish retrieval baselines and NUCourseBench

**Outcome:** every retrieval improvement has a fixed, reviewable comparison set.

1. Build the specified 300-query NUCourseBench: 120 ML/AI/SCAI, 140 across other schools, and 40 ambiguous/unanswerable queries.
2. Split once into 150 training, 50 development, and 100 untouched test items. Manually review development/test labels and keep their provenance.
3. Build the 100-question answer suite and the separate requirement-parser suite described in `AGENTS.md`.
4. Implement PostgreSQL full-text retrieval and record Recall@5, MRR, nDCG@10, exact-code accuracy, no-answer precision/recall, per-school/intent results, confidence intervals, and paired comparisons.
5. Add the frozen `all-MiniLM-L6-v2` candidate only with immutable model/tokenizer revisions and a reproducible save/reload check.
6. Use a public benchmark such as BEIR for general harness smoke checks only. Do not substitute it for the manually reviewed NU-specific set or import its data into the product catalog.

**Exit gate:** test split is untouched; all baseline metrics have raw artifacts and version metadata; exact-code and no-answer behavior are separately measured; benchmark can run offline from committed manifests/fixtures.

### Step 8 — Add the citation-grounded assistant with deterministic fallback

**Outcome:** assistant explanations are evidence-bound; search functionality survives provider failure.

Implement this canonical flow:

```text
intent detection
→ structured SQL filters and exact-code detection
→ lexical and embedding retrieval
→ optional benchmarked reranking
→ deterministic requirement/graph lookup
→ grounded response generation
→ citation and unsupported-claim validation
→ deterministic evidence fallback on failure
```

1. Define typed `/v1/ask` request/response schemas, categorical confidence, interpreted intent/filters, limitations, freshness, and trace ID.
2. Add provider adapters behind FastAPI-owned interfaces. Provide a fake provider for tests and an unavailable provider path for local development.
3. Pass the LLM only the minimum retrieved evidence required for the question; treat source text as untrusted and ignore embedded instructions.
4. Validate every factual claim against citations; preserve requirement Boolean structure and distinguish current from historical offerings.
5. Return deterministic evidence summaries when generation, citation validation, or provider availability fails.
6. Add prompt-injection, missing citation, unsupported claim, hallucinated course/instructor/prerequisite, and provider-timeout tests.
7. Add assistant UI with progressive status, sources, freshness, limitations, trace ID, and per-answer feedback. Do not persist conversation history by default.

**Exit gate:** answer suite meets citation precision ≥0.98 and zero-invention gates before release; fallback tests prove the explorer and deterministic answer path work with no model provider.

### Step 9 — Evaluate trained retrieval and optional reranking

**Outcome:** model training remains an evidence-backed optional improvement.

1. Establish frozen full-text and frozen MiniLM baselines before training.
2. Create relevant pairs and hard negatives from reviewed training data only. Audit likely false negatives before training.
3. Train the MiniLM bi-encoder with deterministic seeds and complete checkpoints, including optimizer, scheduler, scaler, RNG, sampler, epoch, and step state.
4. Validate CPU execution, uneven final accumulation, scheduler/optimizer boundaries, non-finite loss handling, clipping order, and interrupted-versus-uninterrupted parity.
5. Verify hardware before AMP. Start CPU/local; use GPU only for a justified, time-boxed experiment within the approved budget.
6. Evaluate once on development during iteration; compare the final candidate once on the untouched test set after decisions are frozen.
7. Evaluate a cross-encoder reranker only as a separate ablation after retrieval baselines are stable.
8. Ship a trained retriever only if held-out nDCG@10 improves by at least 5% relative to the strongest frozen baseline without regressions in exact-code retrieval, no-answer behavior, or reproducibility. Otherwise publish the negative result and retain the best baseline.

**Exit gate:** benchmark report includes raw JSONL, model/tokenizer revisions, training configuration, seeds, hardware, confidence intervals, and parity results; quality gates determine ship/no-ship.

### Step 10 — Benchmark local serving

**Outcome:** serving choices follow measured need and the same frozen workload.

1. Run the small pinned llama.cpp model on local CPU as the first serving candidate.
2. Use the exact same frozen request set for each engine; record TTFT, TPOT, ITL, end-to-end latency, p50/p95/p99, throughput, goodput, failures, memory, cold start, and warm performance.
3. Keep vLLM/SGLang tests optional and ephemeral; do not stand up production GPU endpoints.
4. Add fake-clock tests for metric formula correctness and include container/model/tokenizer/hardware hashes in artifacts.

**Exit gate:** serving report is reproducible and contains raw results; any cloud GPU experiment has a preflight cost estimate, time limit, export plan, and immediate teardown step.

### Step 11 — Deploy the local-verified system to Azure

**Outcome:** separate Streamlit and FastAPI services run with safe configuration, health checks, observability, and budget controls.

1. Deploy Streamlit and FastAPI as separate containers; Streamlit receives only the FastAPI base URL.
2. Provision PostgreSQL/pgvector and approved source storage only after checking current region pricing, credit balance, and budget category remaining.
3. Use zero minimum replicas where compatible; configure ports, readiness/liveness probes, managed secrets, and OpenTelemetry-compatible logs/traces.
4. Configure budget alerts at 25%, 50%, 75%, and 90%; retain at least the specified $20 buffer.
5. Keep model inference serverless or provider-backed through the FastAPI adapter; do not deploy persistent GPU compute.
6. Add infrastructure-as-code, deployment runbooks, container smoke tests, rollback instructions, and a test that Streamlit cannot access database/provider credentials.
7. Stop for approval if projected spending exceeds any category in `AGENTS.md`.

**Exit gate:** staging smoke test and health probes pass; trace IDs connect UI/API/assistant stages; measured cost remains under budget; deterministic explorer works with the LLM provider disabled.

### Step 12 — Keep NUSpace integration disabled until approved

**Outcome:** product can show an attributed NUSpace link now and optional statistics only after authorization.

1. Keep `StatisticsProvider` disabled and return the documented unavailable response.
2. If written data-sharing approval or a documented API becomes available, implement only that approved interface and retain attribution, sample size, term, and retrieval time.
3. Never scrape the site, reverse-engineer endpoints, or reuse production data under the code repository license.
4. Test the disabled-provider path and prove statistics never affect course or instructor ranking.

**Exit gate:** no live statistics are used without written approval; missing provider cannot break course pages or assistant fallback.

### Step 13 — Run advanced retrieval experiments only after baseline quality gates

**Outcome:** research ideas can be compared without becoming hidden product requirements.

Evaluate one feature at a time, with a frozen benchmark and ablation: cross-encoder reranking, contextual retrieval, late chunking, query rewriting, multi-query retrieval, trained MiniLM, and multimodal document retrieval. Record implementation/runtime cost, latency, memory, failure modes, citation effects, and held-out quality. Do not promote an experiment without a measurable benefit and regression review.

Do not add parallel Chroma or Supabase stores, a Jinja/JavaScript frontend, JWT/password-reset flows, AWS S3/Boto3, GraphRAG prerequisite extraction, agentic retrieval loops, ColPali, or permanent GPU services to v1. LangChain and LangGraph remain optional experiment dependencies rather than architectural requirements.

**Exit gate:** each experiment has a written hypothesis, frozen comparison, raw artifact, and accept/reject decision. The production baseline remains smaller when the benefit is not demonstrated.

## First implementation slice

After resolving Step 0, the first coding session should be a single vertical tracer bullet:

1. Add one sanitized, provenance-bearing schedule fixture.
2. Write one integration test that imports it, validates its checksum/term, and retrieves one normalized course offering.
3. Implement only the model/import/query path needed for that test.
4. Run that test and record the observed RED and GREEN results; do not call a planned or unrun test a pass.
5. Add the next behavior only after the first slice is GREEN.

This proves the source-to-domain path before expanding to the full catalog, API, or UI.

## Cross-phase quality gates

- Every API response and public interface has typed contracts and stable error semantics.
- Every source-derived fact retains provenance and can be traced to the imported snapshot.
- Every feature tests normal, empty, malformed, unavailable, and degraded behavior appropriate to its boundary.
- Requirement parsing and graph traversal use fixtures and property tests; graph correctness never depends on an LLM.
- Retrieval changes include ablations and preserve structured filters, exact course-code retrieval, and no-answer behavior.
- Assistant changes include citation-completeness, prompt-injection, and unsupported-claim fallback cases.
- All tests work without live Registrar, NUSpace, Foundry, Azure, or model services.
- Run the narrowest relevant test during each vertical slice, then `make verify` before a pull request once that command exists.
- Report exactly which commands ran, what passed, and what remains unrun. Do not invent benchmarks, deployment status, screenshots, or metrics.

## Revisit triggers

Revisit this plan when Registrar source formats or automation policy change, NUCourseBench fails to represent real course questions, an approved NUSpace API becomes available, the Azure credit budget or region changes, or a benchmark demonstrates that an optional retrieval/serving feature materially improves the product.
