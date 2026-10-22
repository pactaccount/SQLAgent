# SeaQL — résumé and demo evidence

## Problem and use case
An analyst wants answers from a database without hand-writing SQL. The risk is that generated SQL can be incorrect or unsafe. SeaQL turns questions into queries and puts execution behind a human review step. A realistic enterprise version would also need user authentication, a database allowlist, and read-only credentials.

## Engineering approach
The Python app uses a LangGraph-style text-to-SQL flow, schema context, query execution, retry behavior, and a web review screen. The demo-readiness branch adds server-owned, one-time approval tokens so a browser cannot approve arbitrary SQL merely by editing a request. A sample SQLite database permits a local demonstration without paid model or database setup for the approval tests.

## Hard parts and limits
Text-to-SQL quality must be scored by executed result equivalence, not whether the SQL looks plausible. The approval gate reduces accidental execution risk but is not a complete hosted database security model. No statistically useful execution-accuracy or latency benchmark is published. Existing connected-system tests require model/database services.

## Verification and proof
`./venv/bin/python -m pytest tests/test_approval_gate.py -q` passed 2 offline tests on 2026-10-22. The published proof is [this branch](https://github.com/pactaccount/SQLAgent/tree/demo-readiness-20261022), especially the approval code and tests. The previously recorded Render URL timed out after 50 seconds on 2026-10-22, so use the GitHub link until a complete public question-to-result flow is observed.

## Next measurement and résumé wording
Create a fixed 30–50-question test set with expected result tables, include unsafe requests, and report correct results, rejection rate, retries, p50/p95 latency, and failure examples. Current safe wording: “Built a text-to-SQL workflow with a server-controlled, one-time approval gate and offline tests for token ownership and replay prevention.” Add accuracy numbers only after that benchmark runs.
