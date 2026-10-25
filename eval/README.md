# Evaluation protocol

## Primary evaluation: the actual agent

From the project root:

```bash
.venv-backend/bin/python eval/run_agent_eval.py
```

The runner invokes the same `run_agent` function as the web API, with one configured
NVIDIA model, the application business rules, parsed SQL controls and bounded repair.
No local model, vector database, embedding token or web server process is required.
The configured API is called intentionally. Each run saves a new report under
`artifacts/agent_eval/`; use `--output path.json` only for a new filename. Existing
reports are never overwritten. Reports save atomically after every completed case.

`--validate-only` executes all references with no model calls. `--limit N` permits
1–30 questions for a small run. Provider failure stops further requests and leaves
an incomplete report rather than exhaust quota. Fix provider access before retrying.

## Dataset and semantic contracts

26 SQL cases and four clarification cases come from `business_questions.md`.
`olist_cases.py` supplies reference SQL; it is never sent to the model. Agent-v2
makes Q05's requested columns explicit (product_id, price) and Q24's denominator
explicit (positive review rows / all review rows by buyer cohort). It is a new
benchmark version, not an untouched rerun of the original direct-model baseline.

Reference interpretation:

- Commercial sales use delivered orders; explicit all-order, catalog, payment,
  review, first-purchase and cohort questions retain their stated scope.
- Q05 uses delivered items. Q16 counts all item-bearing multi-seller orders.
- Q10 includes all of 2017 using an exclusive 2018 upper bound.
- Late delivery compares calendar dates. Q25's delay uses calendar days.
- Q15 averages reviews within each order, then weights each order/payment-type once.
- Q21 weights each reviewed order/category once after averaging its reviews and
  returns all qualifying categories. Do not multiply scores by item/payment count.
- Q20 excludes the two zero-installment rows from its four named brackets.
- Q22's first month has NULL growth; Q23 uses dense ranks, including ties.
- Category display prefers English, then Portuguese, then unknown. Numeric missing
  values remain NULL. Zero prices are excluded from freight/price division.

The original questions were inspected during development, so this is a development
benchmark. The ten `final_holdout_questions.md` cases remain outside this runner and
must have independently frozen references before final evaluation.

## Metrics

Result accuracy = reference-matching final results / all completed answerable cases.
Generation, provider and execution failures are unsuccessful cases, not discarded.
An interrupted/provider-blocked run is marked incomplete and is not a full benchmark.
Execution success is reported separately: a query can execute and still be wrong.

Result comparison preserves duplicate rows and column order, ignores row ordering,
and uses numeric relative tolerance 1e-5 or absolute tolerance 0.005. It checks
results on this database instance, not SQL equivalence for all possible data.
Unique column aliases are required. Truncated agent results cannot pass correctness.
The application limit is configurable and defaults to 1,000 rows and ten seconds.
The independent reference runner uses a 10,000-row cap and 20-second limit.

Clarification selection is recorded but completeness needs human review. Review
unsupported assumptions separately. `schema_reference_errors` labels SQLite errors
for nonexistent tables/columns, including intermediate failed attempts; it is not a
general hallucination-rate measure. Reports preserve raw model attempts for review.
Record final-vs-first-attempt outcomes from attempts and review any claimed repair
benefit; executing successfully alone is not proof of recovery to a correct answer.

Each report records dataset, policy, database and source hashes, model configuration,
observed model IDs, retries, raw outputs, errors, result rows and task timings.
Latency is measured around the agent call, not hosted HTTP/UI latency. No token-cost
claim is made because provider usage is not yet captured by this gateway.

## Historical local baseline

`run_local_baseline.py` remains the direct MLX model experiment. Its original saved
report scored 9/26; correcting Q05's reference projection yielded 10/26 (38.5%) when
rescoring unchanged outputs. Both records remain under artifacts/baseline/.

That result is not full-agent accuracy. The API model, prompt and workflow differ;
a score difference must not be attributed solely to agent orchestration.
Do not overwrite or relabel the old baseline as the current application result.
