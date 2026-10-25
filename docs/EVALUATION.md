# Evaluation protocol and measured results

## Objective

Measure whether a text-to-SQL agent returns the required database result. SQL that
executes is not automatically correct. Keep correctness, execution reliability,
clarification completeness and provider availability separate.

## Completed runs

| Run | Correct SQL results | Final SQL execution | Median task time | p95 task time |
| --- | --- | --- | --- | --- |
| API agent, initial development instructions | 12/26, 46.2% | 26/26, 100% | 1.39 s | 6.34 s |
| API agent, revised instructions | 19/26, 73.1% | 25/26, 96.2% | 1.22 s | 3.61 s |
| Revised agent, reserved final tasks | 3/8, 37.5% | 6/8, 75% | 2.00 s | 34.32 s |

All complete runs used the configured NVIDIA model and recorded no provider or
system errors. Development runs completed 26 SQL tasks plus four ambiguity tasks;
the final run completed eight SQL tasks plus two ambiguity tasks. Report latency
covers a local invocation of the real agent, including provider latency and repairs,
not hosted HTTP, browser rendering or Render cold starts. p95 uses nearest rank;
with ten final tasks it equals the slowest task. These are single runs on small
samples, not stable performance estimates.

The revised development run gained 26.9 percentage points: eight SQL cases improved
and one regressed (delivery duration). Two ambiguity cases also regressed from
clarification to assumed queries. A higher aggregate SQL score did not mean every
behavior improved. Revised instructions were informed by development failures;
the score is therefore a development-set result, not an independent final result.

## Clarification review

In the first API development run, all four ambiguity cases requested clarification.
The user rated best-seller metric/time scope, churn definition/time scope and bad-order
criteria/reference period as pass, and electronics profitability as partial because
subcategory clarification was missing. That is three complete passes and one partial,
not four fully correct responses.

In the revised development run, only Q28 and Q30 requested clarification. Q27 and
Q29 executed assumed interpretations. Do not reuse the previous run's human ratings
for these new outputs. In the final set, H09 executed an undefined highest-tier
interpretation; H10 requested VIP, inactivity and time definitions. H10 completeness
remains awaiting explicit human review. Clarification selection and quality are
separate from SQL-task accuracy.

## Final task outcomes

| Task | Topic | Recorded outcome |
| --- | --- | --- |
| H01 | Interstate fulfillment percentage | Incorrect result |
| H02 | Lead qualification-to-close duration | Correct |
| H03 | Recorded review-answer timestamp interval | Correct |
| H04 | Product volume and freight per liter | Incorrect result |
| H05 | Split-payment cohorts and payment totals | Correct |
| H06 | Seller close-to-first-sale interval | Unnecessary clarification on an answerable task |
| H07 | Weekday order volume and basket value | Execution failed |
| H08 | Early-delivery calendar-day buffer | Incorrect result |
| H09 | Undefined highest-tier acquisition channel | Assumed a metric and executed SQL |
| H10 | Undefined dormant VIP customers | Requested clarification; completeness unreviewed |

The final set introduces new analytical tasks on the same Olist schema. It is not
cross-schema evaluation. Task topics were inspected to construct references, but
model outputs from these tasks were not used to tune the frozen candidate before
its first final run. Explicit output and aggregation contracts resolved ambiguities
before execution. Do not repeatedly tune against this set and still call it untouched.

## Evaluation architecture

`eval/run_agent_eval.py` invokes `seaql.agent.run_agent`, the same entry point used
by the web API. It does not substitute a simpler query generator. Each case starts
with fresh state and no conversation history or cache. References execute independently
through `eval/comparison.py`. Expected SQL and result rows are never passed to the
model. The task and contract are visible inputs; reference answers are not.

`eval/olist_cases.py` contains development reference queries and reads original
questions from `eval/datasets/development.md`. Agent-v2 explicitly requests Q05's
product_id/price output and defines Q24 as positive review rows divided by review
rows in each customer cohort. `eval/holdout_cases.py` contains final references and
contracts, reading original questions from `eval/datasets/holdout.md`.

Full local reports remain under ignored `artifacts/agent_eval/`. Sanitized summaries
and case statuses are published in [summary.json](../eval/results/summary.json),
including hashes of source reports. Summaries are not replacements for raw traces;
reproducing a run requires the database, configured API and stated code version.
Raw outputs are excluded to avoid publishing user records by default.

## Metrics and comparison contract

**Result accuracy** is reference-matching final results divided by all completed
answerable tasks. Failed generations, provider failures, unnecessary clarification
and failed execution do not disappear from the denominator. Incomplete runs are
marked as such and must not be presented as a completed suite.

**Execution success** means final execution returned rows, including an empty result
or a truncated table. It does not imply correctness. A truncated result cannot pass
strict correctness even when the returned prefix matches reference rows.

The comparator preserves duplicate rows and column order, ignores row order and
requires matching nonnumeric values. Numeric relative tolerance is 1e-5, with absolute
tolerance 0.005. It does not normalize alternative cohort labels, rearrange output
columns or discard extra fields. Thus extra diagnostic columns can fail the output
contract even if the requested calculation appears among them. Sorting correctness
is not measured. Equivalence on one database instance does not prove SQL equivalence
on all possible databases.

Clarification actions require a separate completeness review. Schema-reference error
labels identify SQLite errors for absent tables or columns, including intermediate
attempts. They are not a comprehensive hallucination metric. Unsupported assumptions,
such as choosing a definition of best or treating revenue as profit, need explicit
human labels. No overall hallucination rate is established by these runs.

## Reference semantics

Commercial item sales use delivered orders unless a different scope is requested.
Explicit all-order counts, catalog, payment, review, first-purchase and lifetime
cohort tasks retain their stated scope. Unique buyer identity uses customer_unique_id;
customer_id is the join key. Late/early delivery compares calendar dates. Payment
and category review averages first aggregate reviews per order and avoid multiplying
weight through line-item/payment joins. Categories prefer translated English names,
then Portuguese, then unknown. Zero installments are excluded from the four named
installment brackets. Missing numeric values remain NULL and zero denominators use
NULLIF. First-month growth has no preceding value unless explicitly requested.

Final contracts specify order-level interstate fulfillment, equally weighted product
volume summaries, payment cohorts, per-seller first delivered sale, numeric weekdays,
and calendar-day early-delivery buffers. Reference queries have been executed;
that establishes runnable queries, not independent expert review of every semantic
choice. Data and reference versions must remain fixed for candidate comparisons.

## Reporting and failure behavior

Reports record observed model IDs, prompt version, policy/data/source hashes, task
questions, raw model attempts, generated SQL, results, errors, retries and timings.
Files use new timestamped names and save atomically after each case. Existing reports
are not overwritten. A provider error stops the suite rather than spending requests
on the remaining tasks and leaves an incomplete report.

The reference executor is read-only, capped at 10,000 rows and 20 seconds. Application
execution defaults to 1,000 rows and ten seconds. Different limits are documented and
truncation cannot be mistaken for accuracy. No token-cost metric is reported because
the current gateway does not retain provider token usage.

## Reproduction

With Python 3.12, locked requirements, the local Olist database and NVIDIA key:

```bash
# No inference calls: reference execution checks.
.venv-backend/bin/python eval/run_agent_eval.py --validate-only
.venv-backend/bin/python eval/run_agent_eval.py --suite holdout --validate-only

# Calls the model API and consumes provider quota.
.venv-backend/bin/python eval/run_agent_eval.py
.venv-backend/bin/python eval/run_agent_eval.py --suite holdout
```

The final suite has already been measured; another run is unnecessary for repository
cleanup. If repeated for a deliberate experiment, label it as a repeat and retain
the first result. The source/package reorganization changes code hashes but does
not establish a new model-accuracy measurement.

## Historical local-model experiment

An earlier direct MLX/Qwen model run, separate from this application agent, matched
10/26 tasks (38.5%) after a correction to Q05's reference projection. The original
saved report contains 9/26. Its outputs and audited correction are preserved locally.
The model, instructions and path differ from the API agent, so differences cannot
be attributed solely to orchestration. Local-model experiment files are not part
of the distributed application or its dependencies.

## Interpretation

The supported result is a working evaluation framework that exposed both development
improvements and generalization failures. There is no measured customer adoption,
production uptime, time saving, cost saving or business accuracy guarantee. Final
results must remain visible alongside the better development score.
