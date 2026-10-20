# UI design research and rationale

This document records the research behind the interface, what was adopted from
it, and what was deliberately left out. It is written for whoever maintains
the UI next, and for reviewers who want to know why things are the way they
are.

Sources are cited inline. Where a product's behaviour is documented, the
link is to the documentation rather than to a summary.

---

## 1. What the market actually does

The two reference implementations are **Databricks Genie** and **Snowflake
CoWork / Copilot**. Both are relevant, but they solve different problems and
their trade-offs are instructive in opposite directions.

### Databricks Genie

Genie is explicitly built for "business users… without navigating technical
concepts like compute, queries, models, or notebooks"
([Genie](https://docs.databricks.com/aws/en/genie/)). It separates surfaces by
audience: **Genie One** is a full-screen, business-facing chat surface;
**Genie Agents** are the per-domain, curated chat spaces; **Genie Code** is
the developer assistant.

The response anatomy is the part worth copying
([talk-to-genie](https://docs.databricks.com/aws/en/genie-agents/talk-to-genie)):

```
Analysis (expandable)
  - Understanding the question
  - Found relevant data
  - Referenced SQL example
  - Thinking steps  ("explain the SQL logic in plain language")
Summary          (auto-generated natural-language summary of results)
Result table
Associated visualizations
Applied filters  (editable values that change the result set)
```

Other notable patterns:

- **Suggested follow-up questions.** "After each response, Genie uses agent
  instructions and conversation context to generate suggested follow-up
  questions" ([talk-to-genie](https://docs.databricks.com/aws/en/genie-agents/talk-to-genie)).
- **Editable SQL.** With CAN EDIT, authors can edit the generated SQL, run
  it, and "Add as instruction" to save the corrected query back
  ([talk-to-genie](https://docs.databricks.com/aws/en/genie-agents/talk-to-genie)).
- **Editable visualisation.** The chart type is changed from a dropdown in a
  side pane ([talk-to-genie](https://docs.databricks.com/aws/en/genie-agents/talk-to-genie)).
- **Copy CSV**, **Refresh data**, **Regenerate response** in a per-response
  kebab menu ([monitor](https://docs.databricks.com/aws/en/genie-agents/monitor)).
- **Common questions** on the chat landing page, with Genie auto-filling
  remaining slots when the author supplies too few
  ([set-up](https://docs.databricks.com/aws/en/genie-agents/set-up)).

### Snowflake

Snowflake has three distinct surfaces, and it is worth not confusing them
([snowflake-copilot](https://docs.snowflake.com/en/user-guide/snowflake-copilot),
[deploy-agents](https://docs.snowflake.com/en/user-guide/snowflake-cortex/snowflake-cowork/deploy-agents)):

| Surface | For | SQL visibility |
|---|---|---|
| Copilot | Next to a worksheet | **Run** / **Add** buttons — the answer is *not* executed until you click |
| CoWork (ex-Snowflake Intelligence) | A standalone branded app | No documented SQL panel; SQL surfaces through citations |
| Cortex Code | In Snowsight | Red/green diff, Accept / Reject |

The decisive pattern from Snowflake: **the generated SQL is not executed
until the user acts on it.** "If the response from Copilot includes SQL
statements: Select **Run** to run the query… Select **Add** to edit the query
before running it."

Also from Snowflake:

- **"Trends and comparisons render as visualizations, while detailed lookups
  return tables"** — the agent chooses the form
  ([CoWork overview](https://docs.snowflake.com/en/user-guide/snowflake-cortex/snowflake-cowork.md)).
- **Interactive results.** "Charts and tables are interactive, so you can
  sort, filter, search, and resize directly without asking a new question."
- **Explained charts.** "with clear explanations about how each chart was
  created" ([CoWork overview](https://docs.snowflake.com/en/user-guide/snowflake-cortex/snowflake-cowork.md)).

### The practitioner's critique

Chastagnol's tour of Snowflake's AI features (Jan 2026) is the sharpest
independent take available, and it lands on the thesis this project is built
around ([source](https://clementc.github.io/blog/2026/01/23/Snowflake_AI_features_tour/)):

> "the chatbot framing can be misleading. The serious work is still data
> modeling, governance, access control, query constraints, evaluation, and
> cost control… **the model is not the product. The system around the model
> is the product**"

> "Snowflake Intelligence is not 'ask anything about all your data'. It is
> closer to 'ask reasonable questions on a well-prepared subset of the data'"

He also praises the deliberate non-inference of joins — "the system does not
automatically infer arbitrary joins on its own, and that is probably a good
thing" — which is the same instinct behind this project's safety gate.

---

## 2. What this project adopted, and why

| Pattern | Source | Implementation here |
|---|---|---|
| Plain-language summary of results | Genie's "Summary" | `insight` — the "What stands out" block |
| SQL shown but not in the way | Genie's "Show code" | Collapsed `<details>` disclosure, always one click away |
| Editable SQL that can be re-run | Genie's "Edit and save queries" | SQL textarea in the disclosure + "Run this SQL" |
| Plain-language explanation of the query | Genie's "Thinking steps" | `sql_explanation` — one sentence, no jargon |
| **Step-by-step breakdown** | **STEPS (EMNLP'23), SQLucid (UIST'24)** | **"How this was worked out"** — the query in plain-language steps |
| Suggested follow-up questions | Genie's suggested follow-ups | Up to 3 chips under each answer |
| Auto-generated starter questions | Genie's "common questions" | `/starter_questions`, generated from the real schema |
| Agent chooses chart vs table | Snowflake's form selection | `detect_chart_type()` + `planChart()` |
| Interactive results — sort, filter, search | Snowflake's "explorer mode" | Sortable, filterable, searchable data grid |
| Copy the SQL | Snowflake's clipboard button | "Copy SQL" in the disclosure |
| User-visible safety gate | *This project's own original* | Impact preview before any write |
| **Categorical confidence, tied to evidence** | **NN/g, PAIR, Steyvers et al.** | **High / Medium / Low badge, derived from the run** |
| **AI-interaction disclosure up front** | **EU AI Act Art. 50** | **A notice above the app, hidden after the first question** |

### The finding that changed the design most

Bansal et al. (CHI'21, ~100 participants per condition, three datasets) found
that explanations "increased the chance that humans will accept the AI's
recommendation, **regardless of its correctness**," and that explaining the
top prediction *worsened* team accuracy when the AI was wrong. Their
conclusion: "explanations increased blind trust rather than appropriate
reliance on AI."

A naive "show the SQL and explain it" implementation reproduces exactly that
failure. Two changes came out of it:

**1. The explanation describes mechanics, not reasoning.** The prompt asks
for what the query mechanically does — which tables it reads, which columns
it selects, what filter it applies — and explicitly forbids justifying the
query. A free-form "here's what I did and why it's right" is a rationalisation
the reader cannot check. A description of the mechanics is checkable line by
line against the SQL, which is right below it.

**2. Confidence is categorical and evidence-based.** Steyvers et al. (Nature
Machine Intelligence 2025, N = 60/60/59) found that "longer explanations
increased user confidence, even when the extra length did not improve answer
accuracy" — human discrimination AUC was 0.54 for long explanations versus
0.57 for uncertainty-only language. The lever that worked was *calibrated
uncertainty language*, not more prose. So the confidence here is High /
Medium / Low, never a percentage, and it is derived from what actually
happened in the run: a retried query is Low, a cache hit is Medium, a clean
first-try run is High. The model is never asked to estimate its own
probability, because it cannot do that well.

### Why the step breakdown is the most important feature

The strongest positive result in the SQL-specific literature is that
editability and decomposition, not display, is what works:

- **STEPS** (Tian et al., EMNLP'23, N = 24, including 10 users who had never
  written SQL) found that editable step-by-step natural-language
  explanations helped users "complete almost 2× and 4× more tasks correctly"
  than the DIY and MISP baselines, "with significantly higher self-reported
  confidence and lower mental load." It is the rare case where accuracy,
  confidence, and mental load all improve together.
- **SQLucid** (Tian et al., UIST'24, 38 participants) reached 85% task
  accuracy against 67% and 56% for the baselines, with self-reported
  confidence of 6.42 against 5.29 and 3.79.
- **Dietvorst et al. (2018)** showed the mechanism behind it: people reject
  algorithms they cannot modify, but adopt ones they can. Given the chance to
  modify, 51–74% chose to use it.
- **Ipeirotis & Zheng** put it in one sentence: "The interface reallocated
  the work of querying rather than removing it: users still had to verify the
  generated SQL, and an NLIDB that hid it would remove the step that let them
  trust the answer."

So the design is: **the steps are the verification surface, the SQL is the
evidence, and the edit box is the repair loop.** Showing the SQL alone is the
weak version of this idea.

**What the literature does *not* support, and this design avoids:**

- **Step-by-step model reasoning.** NN/g is explicit that such walkthroughs
  are "rationalizations generated after the fact, rather than faithful
  representations of how the model arrived at an answer," and recommends
  against explanations that imply transparency. The steps here describe the
  *query*, which is a real artifact that was actually executed — not a
  reconstruction of the model's thinking.
- **Longer explanations.** The length finding above is direct: length raised
  confidence without raising discrimination.
- **Citations as reassurance.** NN/g notes that "including the source
  regardless of its validity, gives users a false sense of reliability," and
  that people rarely click citation links.
- **A confidence percentage.** Fake precision, with the evidence above.

### The regulatory floor

EU AI Act Article 50 has applied since 2 August 2026. Article 50(1) requires
providers to ensure people "are informed they are interacting with an AI
system," and Article 50(5) requires that this be clear and distinguishable
"at the latest at the time of the first interaction." Article 50(4)
additionally exempts text that "has undergone a process of human review or
editorial control" — which is exactly what the editable-SQL approval flow
constitutes.

The notice at the top of the app therefore states what the system is, what it
can get wrong, and what the reader can do about it, and it is shown until the
first question is asked. Research on AI disclaimers is consistent that
generic small-print warnings are ignored; this one names the specific
limitation ("can misread a question") and the specific remedy ("every answer
shows the query it ran").

### The one deliberate departure

Snowflake's Copilot does not run the generated SQL until the user clicks
**Run**. This project executes read-only SQL immediately, because the whole
point is that a non-technical user gets an answer without having to do
anything. The safety boundary is drawn at **read vs write**, not at
"read-only SQL also needs approval" — a table of data with no way to see it
is a worse product than one where a `SELECT` runs on your behalf.

Writes are still fully gated: nothing that changes data runs without an
explicit approval, and the user sees the row count and a sample of the
affected rows first.

### The confirmation dialog

The approval card follows the established confirmation-dialog canon, which
is well documented and largely consistent across the field:

| Rule | Source | Implementation here |
|---|---|---|
| Restate the request and name the object | NN/g, [Confirmation Dialogs](https://www.nngroup.com/articles/confirmation-dialog/) | The title is a question naming the table and the row count: "Delete 12 rows from 'Invoice'?" |
| Use a specific verb, not "OK" or "Yes" | NN/g; [ClickHouse design system](https://clickhouse.design/brand/guidelines/confirmation-dialogs) | The button reads "Delete now". The safe option reads "Keep the data" — a positive action, not "Cancel", which is ambiguous between the dialog and the operation. |
| Never pre-focus the destructive button | NN/g; [saasui.design](https://www.saasui.design/blog/saas-destructive-actions-confirmation-ux-patterns) | Neither button is auto-focused, so a stray Enter keypress cannot delete data. The safe option is styled as the default. |
| State the consequence, and say whether it is reversible | NN/g; GitHub's repo deletion dialog | "This cannot be undone" appears for `DELETE`, `DROP` and `TRUNCATE`, and is deliberately **absent** for `UPDATE` and `INSERT`, where it would be untrue. |
| Do not use "Are you sure?" | NN/g: it gives "no protection at all" | The title names the specific action instead. |
| Do not warn too much | NN/g: over-warning breeds habituation | One card per destructive statement, with a preview that already answers "what would this do". |

**Where the industry goes further, and why this project does not.** GitHub
requires the user to type the resource name for repository deletion, and
Snowflake's Multi-party Approval requires a second person for
privilege-changing operations. Both are appropriate for their blast radius.
This project cannot honestly offer type-to-confirm, because whether a
statement is recoverable depends on the database engine's configuration
(SQLite and PostgreSQL differ on this), not on the application. Offering a
guarantee the system cannot keep would be worse than not offering one.

**What the industry does that this project does not.** Metabase Actions
and the dbt MCP server both document no confirmation step before a write —
this project's impact preview and explicit approval exist precisely to fill
that gap.

---

## 3. Deliberately not implemented

These are real features in the reference products. Each was left out with a
reason, so they are not mistaken for oversights.

| Not implemented | Why |
|---|---|
| **Agent mode / Deep Research** (multi-step, cited reports) | A large feature that needs a planning loop. The single-question path is the core of this product. |
| **Artifacts / saved views** (live-referencing, permission-aware) | Needs a persistence layer and an auth model. A saved question per tab covers the common case for now. |
| **Semantic views / verified-query repository** | Requires a governed metadata layer. This project indexes the raw schema instead, which is a weaker but zero-configuration substitute. |
| **Threaded chat history with rename/delete** | Tabs serve the same purpose within a session. |
| **Sharing / permissions on conversations** | Needs an auth model this project does not have. |
| **Scheduled automations** (recurring email reports) | Out of scope for a local tool. |
| **Slack / Teams integration** | Requires a public deployment and a bot host. |
| **"Add as instruction" / feedback-driven curation** | Would need a place to store curated instructions. The current feedback control logs to the console. |
| **Entity matching** (curated values as filter dropdowns) | Requires per-column curation. The starter questions and schema explorer cover discovery for now. |

---

## 4. Design system

### Colour

The palette is validated, not eyeballed. The categorical chart colours are
checked for lightness band, chroma floor, colour-vision-deficiency
separation, normal-vision separation, and contrast against the actual
surface — in both themes.

| Slot | Light | Dark |
|---|---|---|
| 1 — blue | `#2a78d6` | `#3987e5` |
| 2 — orange | `#eb6834` | `#d95926` |
| 3 — aqua | `#1baf7a` | `#199e70` |
| 4 — yellow | `#eda100` | `#c98500` |
| 5 — magenta | `#e87ba4` | `#d55181` |
| 6 — green | `#008300` | `#008300` |
| 7 — violet | `#4a3aa7` | `#9085e9` |
| 8 — red | `#e34948` | `#e66767` |

Results: light mode passes all checks with a contrast warning on aqua and
yellow (both below 3:1 on white), relieved by the always-present table view
and direct labels; dark mode passes all checks outright against the
`#12161c` surface.

The slot **order** is the colourblind-safety mechanism, so slots are assigned
in sequence and never cycled.

Status colours are a fixed, reserved scale — `good #0ca30c`, `warning
#fab219`, `serious #ec835a`, `critical #d03b3b` — always shipped with an
icon and a label, never colour alone.

### Chart rules

These are not stylistic preferences; each prevents a specific way of
misleading the reader.

- **Nominal categories all take the same colour.** Bar length already
  encodes the value. Colouring by value spends the identity channel on
  information the chart already shows.
- **Never a second y-axis.** Two measures of different scale become two
  charts, or one chart with the values indexed to a common base.
- **Gridlines are solid hairlines**, one shade off the surface. A dashed grid
  reads as a threshold when it is just a grid.
- **A tooltip enhances, never gates.** Every value is also in the table
  below, and the legend is present for two or more series.
- **The chart never replaces the table.** The table is the accessible twin.

### Typography

`Inter` for the interface, `JetBrains Mono` for SQL and code. `tabular-nums`
on table cells and axis ticks, where digits must align vertically — but not
on large standalone numbers, where proportional figures read better.

### Spacing and motion

A 4px spacing scale. Transitions are 120–180ms. All animation is disabled
under `prefers-reduced-motion: reduce`.

---

## 5. Accessibility

Target: **WCAG 2.2 Level AA**.

| Criterion | How it is met |
|---|---|
| **1.4.3 Contrast (Minimum)** | Every text colour meets 4.5:1 (3:1 for large text) against its surface, in both themes. |
| **1.4.11 Non-text Contrast** | Control borders, focus rings and chart marks meet 3:1. |
| **2.1.1 Keyboard** | Every control is reachable and operable by keyboard. |
| **2.4.11 Focus Not Obscured** | The focus ring is drawn outside the element, so it is never clipped by a scroll container. |
| **2.4.13 Focus Appearance** | A 2px accent ring with a 2px surface gap — visible against every surface. |
| **2.5.8 Target Size (Minimum)** | Interactive targets are at least 24×24 CSS pixels. This is why the sort buttons, tab close buttons, feedback buttons and status-bar buttons are sized at 26px or larger even where the visual design would allow less. |
| **1.4.10 Reflow** | The layout reflows to a single column at narrow widths; the side panels become overlays. |
| **4.1.2 Name, Role, Value** | Native `<table>` semantics, `aria-sort` on sorted headers, `role="log"` with `aria-live="polite"` on the conversation, `aria-pressed` on toggles. |

Additional decisions:

- **The data grid is a real HTML table.** Screen readers announce row and
  column headers correctly without a pile of ARIA. The sort direction is
  carried by `aria-sort` on the header cell.
- **Status is never colour alone.** Every badge pairs a colour with an icon
  and a word.
- **Motion respects `prefers-reduced-motion`.**
- **Tooltips are real tooltips**, not `title` attributes, so keyboard users
  can reach them.

---

## 6. Sources

**Databricks**
- [Genie](https://docs.databricks.com/aws/en/genie/) ·
  [Genie One](https://docs.databricks.com/aws/en/genie-one/) ·
  [Chat in Genie One](https://docs.databricks.com/aws/en/genie-one/chat)
- [Talk to Genie](https://docs.databricks.com/aws/en/genie-agents/talk-to-genie) ·
  [Concepts](https://docs.databricks.com/aws/en/genie-agents/concepts) ·
  [Set-up](https://docs.databricks.com/aws/en/genie-agents/set-up) ·
  [Tune quality](https://docs.databricks.com/aws/en/genie-agents/tune-quality) ·
  [Best practices](https://docs.databricks.com/aws/en/genie-agents/best-practices) ·
  [Monitor](https://docs.databricks.com/aws/en/genie-agents/monitor)
- [Genie Ontology](https://docs.databricks.com/aws/en/genie/genie-ontology) ·
  [Dashboards](https://docs.databricks.com/aws/en/genie-spaces/)
- [Release notes, July 2026](https://docs.databricks.com/aws/en/release-notes/product/2026/july) ·
  [Next-generation Genie blog](https://www.databricks.com/blog/next-generation-databricks-genie)

**Snowflake**
- [Snowflake Copilot](https://docs.snowflake.com/en/user-guide/snowflake-copilot) ·
  [Copilot inline](https://docs.snowflake.com/en/user-guide/snowflake-copilot-inline) ·
  [Cortex Code in Snowsight](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-code-snowsight)
- [CoWork overview](https://docs.snowflake.com/en/user-guide/snowflake-cortex/snowflake-cowork) ·
  [Deploy agents](https://docs.snowflake.com/en/user-guide/snowflake-cortex/snowflake-cowork/deploy-agents) ·
  [Artifacts](https://docs.snowflake.com/en/user-guide/snowflake-cortex/snowflake-cowork/artifacts) ·
  [Chart customization](https://docs.snowflake.com/en/user-guide/snowflake-cortex/snowflake-cowork/chart-customization) ·
  [Getting started](https://docs.snowflake.com/en/user-guide/snowflake-cortex/snowflake-cowork/getting-started)
- [Cortex Analyst REST API](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/rest-api) ·
  [Verified Query Repository](https://docs.snowflake.com/en/user-guide/views-semantic/verified-query-repository) ·
  [Suggested questions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/suggested-questions-feature) ·
  [Semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/overview)
- [Snowflake Copilot release notes](https://docs.snowflake.com/en/release-notes/2025/other/2025-11-04-snowflake-intelligence) ·
  [CoWork product page](https://www.snowflake.com/en/product/snowflake-cowork/)

**Standards**
- [W3C ARIA APG — Table pattern](https://www.w3.org/WAI/ARIA/apg/patterns/table/) ·
  [Grid pattern](https://www.w3.org/WAI/ARIA/apg/patterns/grid/)
- [W3C — Target Size (Minimum), SC 2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
- [WCAG 2.2 quick reference](https://www.w3.org/WAI/WCAG22/quickref/)

**Independent**
- [Snowflake AI features tour — Clément Chastagnol, Jan 2026](https://clementc.github.io/blog/2026/01/23/Snowflake_AI_features_tour/)
- [Atlan — Adding context to a Databricks Genie space](https://atlan.com/know/ai-agent/databricks/add-context-to-databricks-genie-space/)

**Trust, verification and explainability — the research behind Section 2**
- [Bansal et al., CHI'21 — "Does the Whole Exceed its Parts?"](https://doi.org/10.1145/3411764.3445717) · [arXiv](https://arxiv.org/abs/2006.14779) — *the negative result: explanations increased blind trust regardless of correctness*
- [Tian et al., EMNLP'23 — STEPS: Interactive Text-to-SQL via Editable Step-by-Step Explanations](https://doi.org/10.18653/v1/2023.emnlp-main.1004) · [arXiv](https://arxiv.org/abs/2305.07372)
- [Tian et al., UIST'24 — SQLucid: Grounding NL Database Queries with Interactive Explanations](https://doi.org/10.1145/3654777.3676368) · [arXiv](https://arxiv.org/abs/2409.06178)
- [Ipeirotis & Zheng — Natural Language Interfaces for Databases](https://arxiv.org/abs/2511.14718) *(preprint)*
- [Dietvorst, Simmons & Massey, 2018 — Overcoming Algorithm Aversion](https://doi.org/10.1287/mnsc.2016.2643) ·
  [2015 — Algorithm aversion](https://doi.org/10.1037/xge0000033)
- [Buçinca, Malaya & Gajos, CSCW'21 — To Trust or to Think](https://doi.org/10.1145/3449287)
- [Vasconcelos et al., CSCW'23 — Explanations Can Reduce Overreliance](https://doi.org/10.1145/3579605) · [arXiv](https://arxiv.org/abs/2212.06823)
- [Schemmer et al., IUI'23 — Appropriate Reliance on AI Advice](https://doi.org/10.1145/3581641.3584066)
- [Steyvers et al., Nature Machine Intelligence 2025 — What LLMs know and what people think they know](https://doi.org/10.1038/s42256-024-00976-7) · [arXiv](https://arxiv.org/abs/2401.13835)
- [Amershi et al., CHI'19 — Guidelines for Human-AI Interaction](https://doi.org/10.1145/3290605.3300233) ·
  [HAX Playbook](https://microsoft.github.io/HAXPlaybook/)
- [Google PAIR Guidebook — Explainability + Trust](https://pair.withgoogle.com/chapter/explainability-trust/) ·
  [Errors + Graceful Failure](https://pair.withgoogle.com/chapter/errors-failing/)
- [NN/g — Explainable AI in Chat Interfaces](https://www.nngroup.com/articles/explainable-ai/) ·
  [AI Chatbots Discourage Error Checking](https://www.nngroup.com/articles/ai-chatbots-discourage-error-checking/) ·
  [AI Hallucinations](https://www.nngroup.com/articles/ai-hallucinations/) ·
  [Prioritize Smarts over Sentience](https://www.nngroup.com/articles/smarts-emotion-trust-ai/)
- [Cabrera, Perer & Hong, 2023 — Improving Human-AI Collaboration With Descriptions of AI Behavior](https://doi.org/10.1145/3579612)
- [IBM Design for AI — Explainability](https://www.ibm.com/design/ai/ethics/explainability)
- [NIST AI RMF 1.0 (NIST AI 100-1)](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf) ·
  [Generative AI Profile (NIST AI 600-1)](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)
- [EU AI Act Article 50 — Transparency obligations](https://artificialintelligenceact.eu/article/50/) ·
  [Article 113 — Application dates](https://artificialintelligenceact.eu/article/113/)
- [C2PA — UX Recommendations for Implementers](https://c2pa.org/specifications/specifications/2.2/ux/UX_Recommendations.html)

**Confirmation dialogs and destructive actions**
- [NN/g — Confirmation Dialogs Can Prevent User Errors](https://www.nngroup.com/articles/confirmation-dialog/)
- [NN/g — 10 Usability Heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/)
- [ClickHouse design system — Confirmation dialogs](https://clickhouse.design/brand/guidelines/confirmation-dialogs)
- [GitHub Docs — Deleting a repository](https://docs.github.com/en/repositories/creating-and-managing-repositories/deleting-a-repository)
- [BigQuery — Dry run queries](https://docs.cloud.google.com/bigquery/docs/dry-run-queries) ·
  [Best practices for cost](https://docs.cloud.google.com/bigquery/docs/best-practices-costs)
- [Snowflake — Multi-party Approval](https://docs.snowflake.com/en/user-guide/multi-party-approval) ·
  [DROP TABLE](https://docs.snowflake.com/en/sql-reference/sql/drop-table)
- [Retool — Query run behaviour](https://docs.retool.com/queries/guides/run-behavior) ·
  [SQL writes](https://docs.retool.com/queries/guides/sql/writes)
- [MySQL Workbench — Safe Update Mode](https://dev.mysql.com/doc/workbench/en/wb-configuration-additional.html)
- [dbt — full_refresh](https://docs.getdbt.com/reference/resource-configs/full_refresh) ·
  [dbt MCP server](https://docs.getdbt.com/docs/dbt-ai/about-mcp)
- [Metabase — Actions](https://www.metabase.com/docs/latest/data-modeling/models/actions/introduction) ·
  [Row and column security](https://www.metabase.com/docs/latest/permissions/row-and-column-security)
- [saasui.design — Destructive action confirmation patterns](https://www.saasui.design/blog/saas-destructive-actions-confirmation-ux-patterns)

**Onboarding**
- [Metabase — Setting up Metabase](https://www.metabase.com/docs/latest/configuring-metabase/setting-up-metabase)
- [Hightouch — Create a destination](https://hightouch.com/docs/get-started/create-a-destination)
- [Amplitude — The aha moment](https://amplitude.com/blog/aha-moment) ·
  [Getting started: activation](https://amplitude.com/blog/getting-started-activation)
- [PostHog — Building product empty states](https://github.com/PostHog/posthog/blob/master/.agents/skills/building-product-empty-states/SKILL.md)
- [Mixpanel — Onboarding playbook](https://docs.mixpanel.com/guides/strategic-playbooks/onboarding-playbook)
- [DataGrip — Quick start](https://www.jetbrains.com/help/datagrip/quick-start-guide.html)

**Evidence gaps**

No substantive Hacker News, Reddit, or Gartner Peer Insights review of
either product was found. The design decisions above rest on vendor
documentation and one independent practitioner critique, not on user
research. Treat the "why" as well-argued but not user-validated.

Three further gaps are worth stating plainly, because they bound what can
be claimed:

1. **No study measures automation bias with LLM-generated SQL specifically.**
   The nearest evidence is Bansal et al. (explanations, not SQL) and
   Ipeirotis & Zheng (verification reallocation in an NLIDB).
2. **No industry or field study of showing SQL to business users measures
   trust or error detection.** The academic studies are lab-based and use
   SQL-familiar or SQL-novice participants on benchmark tasks.
3. **TURING (ACL 2021)** — the system that shows several candidate SQL
   hypotheses with their differences highlighted — has no user study and no
   N in the paper. Its *design pattern* is worth borrowing; its effect size
   is not established. This project deliberately did not implement
   multi-hypothesis SQL on that basis.

Two widely-repeated attributions could not be verified and are therefore not
cited above: the often-quoted "Why Are We So Bad at Preventing Data Loss?"
and the "Scott Adams on writing confirmation dialogs" post. Neither could be
found in its author's archive, sitemap, or the Wayback Machine. The nearest
verifiable substitute carrying the same thesis is the [ALIVE Design Library
entry on confirmation and the undo principle](https://alivedesignlibrary.com/entries/confirmation-and-the-undo-principle.html).
