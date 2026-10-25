# SQLagent application audit — 2026-10-24

> Historical audit: recorded before the scope was narrowed to single-model text-to-SQL evaluation. This is an issue inventory, not a current feature commitment. The agreed scope is single-model text-to-SQL evaluation.

## Scope and evidence

Reviewed app.py, agent.py, tools.py, vector_store.py, static/app.js,
static/index.html, Dockerfile, ignore files, dependency declarations and tests.
Ran API TestClient checks, SQLite probes on disposable databases, mocked-provider
graph runs, package consistency checks and JavaScript syntax validation. No real
provider calls, changes to the master Olist database or Docker build were made.
Browser interaction, real hosted inference, successful cloud retrieval and remote
database integrations remain unverified. A page returning HTTP 200 is not browser
or model end-to-end validation.

Evidence: artifacts/audit/component_checks.json and graph_checks.json.

## Confirmed working

- Metal inference previously completed; original model smoke and baseline exist.
- Both Python environments report no broken installed package requirements.
- Root and Olist schema endpoints return 200; 11 tables are enumerated.
- 26 baseline reference queries execute. Corrected saved-output score is 10/26.
- Six selected offline tests pass: approval contracts, vector-store configuration,
  SQL reading and mutation interception for tested keyword statements.
- A mocked graph recovers from one invalid-column query and returns correct rows.
- JavaScript syntax check passes.

## Defects and durable remediation

1. Startup depends on import-time Qdrant construction; configured remote access
   returned 403 in the prior direct check. Cause beyond denied access is unknown.
   Move service creation into an application lifecycle, validate configuration,
   expose readiness, and support explicitly configured persistent local storage.
   Use a Qdrant server with a volume when multiple processes/hosts are required.
   Keep optional cache failure separate from core SQL availability.
2. Installed qdrant-client has query_points but no search method. Both retrieval
   and cache reads call search and suppress exceptions. Migrate the client API,
   lock dependencies, test real local indexing/search/cache round trips.
3. Without HF_TOKEN no encoder is created. /connect reports indexing success
   despite no indexed vectors; generation continues with "No schema available".
   Provide a local embedding backend, truthful indexing counts/status and direct
   database-schema fallback. Index changes atomically rather than delete first.
   Include necessary join tables and validated relationships, not arbitrary top-5.
4. Olist is 112,701,440 bytes versus a 26,214,400-byte upload cap. Invalid SQLite
   bytes are accepted based on suffix alone. Add configured bounded uploads,
   SQLite validation, durable catalog/storage and cleanup. Register local Olist
   server-side by connection ID; do not require repeated uploads.
5. API accepts caller-supplied database URI and tenant ID. These are not verified
   identities. Browser persists credential-bearing URIs in localStorage. Use a
   server-side connection registry and scoped sessions; allowlist local paths and
   supported remote connections. Add real user authorization before shared hosting.
6. SQL mutation detection is a keyword regex. PRAGMA user_version=42 executed
   without approval on a disposable database. SELECT 'update' incorrectly requests
   approval. Add single-statement parsing and default-deny classification plus
   database-enforced read-only ordinary execution. Approved writes use a separate
   controlled path, disposable demo copy, audited transactions and cache invalidation.
   Bound query runtime, result rows and synthesis input; dispose engines reliably.
7. Approval tokens are server-owned and single-use but memory-only, not scoped to
   an authenticated session and not shared across workers. Persist pending actions
   and outcomes with atomic state transitions and ownership/expiry checks. Distinguish
   failure, expiry and successful execution; audit all write outcomes.
8. Cached answers are keyed by tenant and semantic similarity, not database,
   schema/model/prompt versions or data freshness. Hits omit result rows; stale
   answers are not re-executed. Cache failure aborts otherwise successful answers
   (reproduced with injected cache failure). Prefer exact-key SQL caching with
   connection/version scoping and re-execution; make optional caching fail softly.
9. Application uses hardcoded hosted NVIDIA inference; local MLX benchmark is a
   separate pipeline. No integrated local model, role-based routing, approved
   business policy, structured clarification state or conversation memory exists.
   Introduce one configured model gateway and structured SQL/clarification outputs.
   Use the same policy and execution contracts for application and evaluation.
10. Retry repairs SQL errors, not semantic mistakes; provider errors bypass that
    path. Include failed SQL explicitly, classify failure types and bound retries.
    Preserve successful raw results if answer synthesis or optional cache fails.
11. UI has global connection state and routes asynchronous responses to whichever
    tab is active on completion. No server conversation history exists. Capture
    originating session per request; scope connection/history/results per session.
    Handle non-2xx approval/rejection/schema responses, clear stale charts, render
    database names/errors as text instead of HTML. Guard optional 3D/chart libraries:
    unavailable THREE currently throws before core UI initialization.
12. PostgreSQL/MySQL appear in UI but their default drivers are not installed.
    Install tested driver extras and encode credentials correctly, or mark those
    connectors unavailable. Snowflake package presence does not verify connectivity.
13. venv executable wrappers point to the old directory. Recreate a backend
    environment from locked requirements; retain the working separate MLX env.
    Use project-relative paths for templates/static/config; current paths depend
    on launch directory. Replace obsolete GEMINI-only .env.template.
14. requirements.txt uses broad minimums. Docker COPY includes new MLX environment,
    model weights and artifacts because .dockerignore lacks them. Lock backend
    dependencies and exclude generated assets; package MLX serving separately on
    macOS rather than assuming it runs in the Linux application container.
    Docker CLI exists but daemon is unavailable, so image build is unverified.
15. Five legacy agent tests fail because run_agent now requires tenant_id and
    db_uri. Remaining backend model tests are not zero-credit offline tests.
    Separate deterministic tests, explicitly opted-in live model tests and actual
    browser tests. Add database isolation, retry exhaustion, invalid uploads,
    cache identity/failure, restart persistence and session-ownership tests.

## Repair order and completion gates

1. Reproducible environment, explicit lifecycle/configuration, persistent storage,
   registered Olist connection and real schema/embedding round trip.
2. SQL execution restrictions, approval persistence/ownership, bounded results and
   versioned connection-scoped caching. Verify on disposable database copies.
3. Unified inference gateway, local MLX serving, structured clarification, retry
   contracts, policy consistency and answer failure handling.
4. Session-correct UI, connector availability, truthful errors, browser walkthrough.
5. Offline regression suite, restart checks, opt-in live end-to-end benchmark and
   deployment packaging. Only then prepare training and compare model versions.

User actions now: none required to diagnose or implement these repairs. Do not
rotate credentials merely to bypass the architectural problems. Later the user
can run prepared model-serving/long benchmark commands and browser acceptance
steps. A real cloud Qdrant deployment needs a working cluster/key only if chosen;
secrets stay in local configuration, never chat.
