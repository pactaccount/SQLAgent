# SeaQL — evaluation results and limitations

## Project claim

A text-to-SQL prototype with execution-based evaluation: questions are translated
into SQL, actual results are compared against references, and failures and
clarification behavior are recorded. Fine-tuning, model routing and autonomous
learning are outside the agreed scope.

## Existing measurements

- Direct local-model benchmark: 30 cases completed, including 26 answerable SQL tasks
  and four clarification cases.
- Model: pinned four-bit Qwen2.5-Coder-7B-Instruct through MLX on the local Mac.
- Original saved report: 9/26 SQL tasks matched its original references.
- Audited score: **10/26 (38.5%)** after Q05's reference projection was corrected.
  The generated output was not changed; original and audited records are preserved.
- Clarification review: Q27 fail, Q28 partial, Q29 partial, Q30 fail. Do not count
  partials as fully correct or report a complete hallucination-rate measurement.
- Ten additional questions are reserved from training and tuning, but have not
  produced a final evaluated score.

Local evidence paths (ignored artifacts may not exist in a fresh clone):

- artifacts/setup/model_manifest.json
- artifacts/setup/inference_smoke.json
- artifacts/baseline/base.json
- artifacts/baseline/reference_audit.json
- eval/clarification_review.md
- final_holdout_questions.md

## Interpretation

This is a small fixed-schema baseline of the local model, not deployed application
accuracy or evaluation of the revised LangGraph workflow. The benchmark was inspected
during development; do not call it an independent final test. Result comparisons do
not test row ordering or prove correctness on all database instances.

Current verification: 50 offline regression tests pass; all 26 reference queries
validate; one real NVIDIA API-backed run_agent task matched its reference result
(artifacts/agent_eval/integration_smoke.json). This is a smoke check, not a measured
full-agent accuracy score. The first complete 30-case API agent evaluation is recorded below. No live deployment is verified by this document.

## Current safe wording

“Built a text-to-SQL prototype and execution-based evaluation harness; measured
38.5% result accuracy on a 26-question Olist local-model baseline and reviewed
clarification failures.”

For a short description without the baseline number:

“Developed a text-to-SQL prototype with reference-result evaluation and per-question
records of incorrect results, execution errors and clarification behavior.”

## Completion evidence still required

An evaluator invoking the real application agent, passing repaired regression tests,
frozen final reference answers, a final per-case report, and a demonstrated hosted
question-to-result workflow. Update wording only after those checks are complete.

## First complete API-backed agent evaluation

Report: `artifacts/agent_eval/20261025T001958643246Z.json`.

- Completed all 30 cases with no provider or system errors.
- Strict final-result correctness: **12/26 (46.2%)**.
- Successful final SQL execution: **26/26 (100%)**, including incorrect and truncated results.
- Four of four ambiguity cases returned clarification. User review: three pass, one partial (Q30), or 75% fully correct clarification responses.
- Median task latency: **1.39 seconds**; nearest-rank p95: **6.34 seconds**.
- Four answerable cases required repair attempts (Q09, Q14, Q22, Q25). Q09 and
  Q14 finished correct; Q22 and Q25 executed but failed strict result comparison.

Common failures include customer-key confusion, omitted delivered-order filtering,
calendar-date comparisons, aggregation grain, top-N scope and unwanted output
columns. Q22 contains the correct growth values but includes an extra revenue
column, so its strict output contract fails. Q16 returns grouped counts instead of
a scalar and reaches the row limit. No overall hallucination rate is established.

This is the application agent invoked locally through the NVIDIA API, not a hosted
HTTP/browser benchmark. It is not directly comparable to the local Qwen baseline:
the model, prompt, benchmark wording and workflow differ. Preserve it before changes.

## Development candidate: sqlite-v3

The reviewed first agent run remains unchanged. Its separate `.review.json` records
user ratings Q27 pass, Q28 pass, Q29 pass, Q30 partial.

The next development candidate strengthens shared business-rule instructions for
join keys, first purchases/cohorts, aggregation grain, date comparisons, status scope,
category translation, requested output fields and clarification completeness. A
final-generation checklist applies these rules using the same model and one call
per attempt. No reference SQL or result rows are inserted into prompts.

The 30-case dataset, references and scoring remain unchanged. These cases have
informed the instructions, so any improvement is a development-set result. The ten
reserved final questions remain untouched. Candidate effectiveness is unmeasured
until the next run; the change is prompt conditioning, not fine-tuning or learning.

## Second development run: sqlite-v3

Report: artifacts/agent_eval/20261025T002723353395Z.json. All 30 cases completed.
Strict result correctness rose from 12/26 (46.2%) to 19/26 (73.1%), a gain of
26.9 percentage points. Eight SQL cases improved and Q12 regressed. Final SQL
execution succeeded for 25/26 (96.2%); Q24 asked unnecessary clarification after
an execution error. Median latency was 1.22 seconds and p95 was 3.61 seconds.
No provider/system errors were recorded. These are single development runs, not
statistically established performance or isolated causal improvement.

Clarification regressed: Q27 and Q29 executed assumed interpretations. Q28 and Q30
requested clarification but their completeness has not been user-reviewed for this
run. Do not carry the previous run's human ratings onto these new responses.

The sqlite-v3 candidate is frozen for the final ten-question suite. No further
prompt changes are made before that run. eval/holdout_cases.py fixes references
and explicit output/aggregation contracts before model execution. These resolve
ambiguous grains and labels in the original questions and are visible to the model.
Holdout question topics were previously inspected for dataset preparation, but no
model outputs from them have informed tuning. The suite tests new tasks on the same
Olist schema; it does not establish cross-database generalization. A reference
execution check establishes runnable SQL, not independent expert validation.

## CSV application support

CSV validation and conversion are covered by offline tests and use no model calls.
The application selects generic schema instructions for standalone CSV tables. For
the Olist table set, sqlite-v3's policy and generation checklist remain unchanged.
No Olist evaluation accuracy is inferred from the CSV tests.
