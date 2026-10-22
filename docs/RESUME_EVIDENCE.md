# SeaQL — résumé and demo evidence

## Problem and real use
Analysts often need answers from databases without writing SQL. SeaQL reads schema context, generates a query, executes it, and returns the SQL and result table so a human can verify the answer. The public demo accepts a sample SQLite database. A real organization would also need authentication, database allowlists, read-only service accounts, and stronger per-user isolation.

## Engineering approach
The deployed FastAPI/LangGraph workflow reads schema, generates SQL with Gemini, retries database errors, runs read queries, and presents answer text, result tables, charts, and SQL in a browser. Mutating statements go through a preview and explicit approval path. The repo includes a deterministic mock model for zero-credit tests. The included [Chinook sample database](../chinook.db) and its [license notice](../CHINOOK_LICENSE.md) make the demo reproducible from a fresh clone.

## Problems encountered
The hosted instance took about 63 seconds to wake on 2026-10-22. A nine-question read-only Chinook evaluation completed four questions correctly, then hit Gemini's free-tier five-request rate limit on five cases. Those five are **not** wrong SQL answers; they are unavailable responses. The API now returns HTTP 429 with a retry message instead of exposing a raw provider traceback as HTTP 500. The public demo's approval flow is a review aid, not a security boundary for untrusted multi-tenant databases.

## Measured proof
The [fixed cases](../benchmarks/chinook_cases.json), [runner](../benchmarks/evaluate_hosted.py), and [per-question hosted report](../benchmarks/results/hosted_2026-10-22.json) show **4/4 correct executed results among completed questions, 5/9 rate-limited, and 4/9 end-to-end completion** on a single run. The set is small and cannot establish general text-to-SQL accuracy. `MOCK_LLM=1 python -m pytest -q` passed 38 deterministic tests (6 skipped) on the deployed main code. The [hosted demo](https://seaql.onrender.com/) accepted a synthetic three-row SQLite file, exposed its schema, and returned the correct CA order total of 25.

## Résumé use
Link this GitHub evidence page and the hosted demo together. Safe wording: “Built a deployed text-to-SQL workflow with schema-aware generation, SQL previews, result tables, and a human review step; verified executed results on a fixed Chinook sample.” Do not claim 100% accuracy, enterprise security, or improved analyst productivity. For a stronger result, run a larger held-out question set with a provider quota that can complete it, and report execution accuracy, completion rate, p50/p95 latency, and unsafe-query rejection separately.
