# SeaQL: Text-to-SQL Prototype

A FastAPI and LangGraph demo for natural-language questions over a selected database. It can retrieve relevant schema from Qdrant when an embedding endpoint is configured, generate SQL with Gemini, retry after execution errors, and cache successful answers. The UI shows generated SQL and query results.

## Review gate

Data-changing statements are intercepted for human review. The server now stores the drafted SQL and database URI behind a random approval ID that expires after ten minutes. Approval executes that stored statement once; the browser cannot replace it with a different SQL string. Rejection removes the pending statement. SQLite uploads receive server-generated filenames and a 25 MB size limit.

This is a **demo review gate**, not a security boundary for an untrusted multi-tenant database service. There is no user authentication or database allowlist; deploy it only with databases and credentials you control. The SQL keyword check is not a parser, so use a read-only database account when testing against remote systems. Do not present this project as zero-trust or enterprise-secure.

## Evidence and limits

`tests/test_approval_gate.py` checks token ownership, one-time execution, and rejection without model calls. `run_usecase_evals.py` is a small connected-system exercise for execution, retries, cache, and review behavior; it does not publish a statistically meaningful execution-accuracy result. Existing `tests/test_agent.py` and `tests/test_backend.py` require model and database services and should be treated as integration tests.

## Run locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.template .env
uvicorn app:app --reload
```

Configure `GEMINI_API_KEY` and, for vector search, `HF_TOKEN` and optional `QDRANT_URL` / `QDRANT_API_KEY`. Without `HF_TOKEN`, the code does not embed schemas or populate the semantic cache. The default in-memory Qdrant instance is reset when the process exits.

Open `http://localhost:8000`. Upload a SQLite database or connect to a database you own. Run the zero-credit review-gate tests with `pytest tests/test_approval_gate.py -q`.

## Next engineering milestone

Add authenticated users, a database allowlist, read-only credentials for ordinary queries, a SQL parser with one-statement enforcement, and a fixed Text-to-SQL benchmark with expected result sets before offering this as a hosted database service.

## Résumé evidence

[Résumé evidence and verification](docs/RESUME_EVIDENCE.md) records the use case, engineering approach, test status, measured results, limits, and safe résumé wording.
