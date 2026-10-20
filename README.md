# Autonomous SQL Agent

Ask a question in plain English. Get an answer, a result table, a chart, and the
exact SQL that produced them — with nothing changed in your database without
your explicit approval.

Built with FastAPI, LangGraph, Google Gemini, Qdrant and vanilla ES modules.
No build step: `pip install -r requirements.txt`, run the server, open the page.

---

## Contents

1. [What it does](#1-what-it-does)
2. [Quick start](#2-quick-start)
3. [The interface, panel by panel](#3-the-interface-panel-by-panel)
4. [A walkthrough for a first-time user](#4-a-walkthrough-for-a-first-time-user)
5. [Connecting a database](#5-connecting-a-database)
6. [Asking questions that work](#6-asking-questions-that-work)
7. [Reading the results](#7-reading-the-results)
8. [The SQL panel](#8-the-sql-panel)
9. [Changes to your data: the approval flow](#9-changes-to-your-data-the-approval-flow)
10. [The schema explorer](#10-the-schema-explorer)
11. [Keyboard shortcuts](#11-keyboard-shortcuts)
12. [Accessibility](#12-accessibility)
13. [How the agent works](#13-how-the-agent-works)
14. [API reference](#14-api-reference)
15. [Architecture](#15-architecture)
16. [Testing](#16-testing)
17. [Troubleshooting](#17-troubleshooting)
18. [Deployment](#18-deployment)

---

## 1. What it does

The agent answers questions about **your** database. You ask in English; it
finds the relevant tables, writes SQL, runs the SQL, and explains the result.

Four things make it different from a chat box bolted onto a database:

| Feature | What it means for you |
|---|---|
| **Schema-aware** | It looks up your real table structure before writing SQL, so it does not invent a column that does not exist. |
| **Self-healing** | If the SQL fails, the agent reads the database's error, fixes its own query, and retries — up to three times — before you ever see a failure. |
| **Read-only by default** | Any statement that would change data is intercepted. You see exactly what it would do, how many rows it would touch, and a sample of them, before it runs. |
| **Verifiable** | The SQL is always one click away. You can read it, edit it, re-run it, and copy it into your own SQL client. |
| **Plain-English** | Every answer comes with a one-line explanation of what the query did, and a "What stands out" line naming the single most interesting fact in the data. |
| **Guided** | Starter questions are generated from your actual schema, so you always have something meaningful to ask. |

Supported databases: **SQLite** (file upload), **PostgreSQL**, **MySQL**, and
**Snowflake**.

---

## 2. Quick start

### Requirements

- Python 3.9+
- A Google Gemini API key
- Optional: a Qdrant Cloud cluster (free tier is fine) and a Hugging Face token
  for semantic search and caching. Without them the app still works — it falls
  back to an in-memory store and reads the full schema instead of retrieving
  the relevant part.

### Install and run

```bash
git clone https://github.com/yourusername/autonomous-sql-agent.git
cd autonomous-sql-agent

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.template .env
# Edit .env and add your GEMINI_API_KEY.
# Optional: QDRANT_URL, QDRANT_API_KEY, HF_TOKEN

uvicorn app:app --reload
```

Open **http://localhost:8000**.

### Try it without any setup

The project ships with `chinook.db`, a sample music-store database. In the
connection wizard choose **"A database file on my computer"** and either:

- upload `chinook.db` from the project folder, or
- type the path `chinook.db` (relative to the server's working directory).

You can then ask "How many albums are there?" and the agent will walk you
through the whole flow.

### Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | yes | The model that writes the SQL. |
| `MODEL` | no | Which model to use. Defaults to `gemini/gemini-2.5-flash`. |
| `MOCK_LLM` | no | Set to `1` to run without a model, using deterministic responses. |
| `QDRANT_URL` | no | Qdrant Cloud cluster URL. Falls back to in-memory. |
| `QDRANT_API_KEY` | no | Qdrant Cloud API key. |
| `HF_TOKEN` | no | Enables the hosted embedding endpoint. Falls back to a local encoder. |
| `FRONTEND_URL` | no | Restricts CORS to one origin. Defaults to `*`. |
| `PORT` | no | Port for the Docker image. Defaults to `8000`. |

**Without Qdrant or a Hugging Face token the app still works.** The vector
store falls back to an in-memory implementation, and the embedder falls back
to a local one. Schema retrieval then matches on keywords rather than
meaning — less precise, but the app is fully functional.

---

## 3. The interface, panel by panel

The app is a three-panel workspace, like a database IDE.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  SQL Agent        ● sqlite · default_tenant        [Connect] [☀]         │  ← top bar
├────┬───────────────┬──────────────────────────┬──────────────────────────┤
│    │               │  Query 1  +                │  Ask                    │
│ ▣  │  DATABASE     ├──────────────────────────┤                          │
│    │               │  SQL                      │  You: How many albums?  │
│ 💬 │  ▸ Album  11  │  ┌──────────────────────┐ │                          │
│    │    AlbumId     │  │ SELECT COUNT(*)      │ │  AI: There are 347.     │
│    │    Title       │  │ FROM Album           │ │                          │
│    │    ArtistId    │  └──────────────────────┘ │  ▸ View the SQL         │
│    │               ├──────────────────────────┤                          │
│    │  ▸ Artist  4  │  RESULTS                  │  [Ask a question…    ]  │
│    │    ArtistId    │  ┌──────────────────────┐ │                          │
│    │    Name        │  │  [chart]              │ │                          │
│    │               │  │  AlbumId │ Title      │ │                          │
│    │               │  └──────────────────────┘ │                          │
├────┴───────────────┴──────────────────────────┴──────────────────────────┤
│  ● sqlite        347 rows        1.2s                    Autonomous       │  ← status bar
└──────────────────────────────────────────────────────────────────────────┘
     ↑ activity rail   ↑ explorer    ↑ SQL + results      ↑ conversation
```

### The top bar

| Element | What it does |
|---|---|
| **Connection chip** | Shows the database type and workspace. A green dot means connected. Click it to change database. |
| **Connect a database** | Opens the connection wizard. |
| **☀ / ☾** | Switches between dark and light. Both themes are designed separately, not inverted. |

### The activity rail (far left)

Two buttons that toggle the side panels. They are highlighted when their
panel is open.

### The left panel — Database explorer

Every table in your database, with its columns and types. Click a table to
expand it. Click a column to ask the agent about it. Double-click a table to
see a sample of its rows.

### The centre panel — SQL and results

- **Tabs** across the top are independent query sessions. Each keeps its own
  SQL, results and conversation. `+` starts a new one.
- **SQL** shows the statement the agent ran.
- **Results** shows a chart (when the data suits one) and the data table.

### The right panel — the conversation

This is where you work. Type a question, press Enter, and the agent answers
here. The result table also appears in the centre panel; the conversation
carries the reasoning.

Each answer comes with:

- **Status badges** — whether it came from the cache, whether the agent had to
  correct itself, how many rows came back, and a confidence signal when it
  matters.
- **The answer** — a sentence. Sometimes two.
- **What stands out** — the single most interesting fact in the data.
- **How this was worked out** — the query broken into plain-language steps, so
  you can check it one operation at a time.
- **The SQL** — collapsed. Open it to read, edit, re-run, or copy it.
- **Try asking** — up to three follow-up questions you could ask next.
- **Copy answer / Ask again**.

The **download** icon in the panel header exports the whole conversation as a
text file.

### The status bar

The live connection state on the left, the row count of the last result, how
long the last question took, and the operating mode on the right.

---

## 4. A walkthrough for a first-time user

You have never used this tool. Here is the shortest path to a useful answer.

**Step 1 — Connect.** Click **Connect a database**. The wizard has three steps:
pick the kind of database, add the details, review. For the quickest start,
choose *A database file on my computer* and upload `chinook.db`.

**Step 2 — Look at what is there.** The left panel fills with your tables.
Expand one. That is your map — you can see every table and column before
asking anything.

**Step 3 — Ask a starter question.** Under the welcome message you will see
suggested questions, generated from your actual schema. Click one. It is
already answered, so you can see what a good result looks like.

**Step 4 — Ask your own.** Type it in the box at the bottom right. Something
concrete works best:

> "Which artist has the most albums?"

> "What is the average invoice total?"

> "List the 10 longest tracks"

**Step 5 — Read the answer.** Three parts come back:

- **The answer** — a sentence. "Artist 82 has the most albums, with 8."
- **What stands out** — the single most interesting fact in the data.
- **The SQL** — collapsed by default. Open it to see exactly what ran.

**Step 6 — Check it.** Click **View the SQL that was run**. It should look
sensible. If a column name looks wrong, you now know the question was
ambiguous, and you can rephrase it.

**Step 7 — Export if you need to.** Use the **CSV** or **JSON** button above
the results table.

That is the whole loop. Everything else in the app is optional.

---

## 5. Connecting a database

Open the wizard with **Connect a database**, the connection chip, or
`Ctrl/Cmd + ,`.

### Step 1 — Pick the kind

Four choices, described in plain language:

| Choice | Use it for |
|---|---|
| A database file on my computer | A `.db`, `.sqlite` or `.sqlite3` file. Drag and drop it in. |
| PostgreSQL | A hosted Postgres database. |
| MySQL | A hosted MySQL database. |
| Snowflake | A Snowflake warehouse. |

### Step 2 — Add the details

**For a file:** drag it onto the drop zone, or click to browse. You can also
type a path if the file is already on the server's machine.

**For a server database:** you need the host, port, username, password and
database name. The port is filled in for you (5432 for Postgres, 3306 for
MySQL). The **Continue** button stays disabled until the required fields are
filled in.

**For Snowflake:** the account identifier (`myorg-myaccount`), username,
password, database, schema and warehouse. You can paste a full Snowflake URL
into the account box — it is cleaned up for you.

**Workspace name** is optional. It keeps one database's schema separate from
another's on the same server. Leave it blank unless you were told otherwise.

### Step 3 — Review and connect

A summary of what you entered, and a note that the agent can only read your
data unless you approve a change. Click **Connect**.

The app reads your table structure and indexes it. This takes a moment for a
large database.

**If the connection fails:** the message says what went wrong — a bad password,
a host that cannot be reached, or a database that does not exist. Your
details stay in the form, so you can correct one field and try again.

---

## 6. Asking questions that work

The agent is good at questions that name **what you want** and let the
database supply the rest. These work well:

| Instead of | Ask |
|---|---|
| "Show me the SQL stuff" | "Which genre has the most tracks?" |
| "Revenue by region please" | "What is the total revenue for each billing country?" |
| "Which one is the best?" | "Which artist has the most albums, and how many?" |
| "Top customers" | "Which 10 customers have spent the most?" |

Things that help:

- **Be specific about the measure.** "Total revenue" beats "sales".
- **Say how many.** "Top 5" and "the last 12 months" change the answer.
- **Name a field you can see** in the explorer, and the agent will use the
  right column.
- **One question at a time.** The agent answers the question it was asked
  rather than guessing at several.

**When a question is ambiguous** — "which product is doing the best?" — the
agent picks the most reasonable reading and tells you the SQL it used. That
transparency is the point: check the SQL, and if the reading was wrong,
rephrase.

---

## 7. Reading the results

### The chart

A chart appears above the table **only** when the data has a shape worth
plotting: a category against a measure (bars), or a date against a measure
(line). A plain list of names gets no chart, because a chart would add
nothing.

- Click **Bars** or **Line** to switch between them.
- Every bar is the same colour on purpose. The bar's length already shows
  the value; colouring by value would say the same thing twice.
- Hover any point for the exact number. Every value is also in the table
  below, so nothing is only reachable by hovering.

### The table

| Control | What it does |
|---|---|
| **Column headers** | Click to sort. Click again for descending, a third time to clear. `NULL` always sorts last. |
| **Filter rows** | The search box filters across all columns as you type. |
| **CSV / JSON** | Downloads the current result set. |
| **First / Previous / Next** | Pages through long results, 100 rows at a time. |

Numbers are right-aligned and use thousands separators. `NULL` is shown in
italics, so empty values are never confused with the text "NULL". A cell
containing long text is truncated with an ellipsis — hover it to see all of
it.

If the server truncated a very large result, the footer says so.

---

## 8. The SQL panel

The centre panel's top half shows the SQL the agent ran. It is always
available and never in the way.

- **Read it.** It is the query behind the number in front of you.
- **Edit and re-run.** This is the repair loop. If the agent picked the wrong
  column, or you want a different filter, change the SQL and press **Run this
  SQL**. The result table updates. Nothing is sent to the agent — it goes
  straight to the database, as a read-only statement.
- **Copy it.** The **Copy SQL** button puts it on your clipboard.
- **Take it elsewhere.** Paste it into your own SQL client, a BI tool, or a
  scheduled job. It is ordinary SQL, not a special dialect.

Inside the disclosure you will also find:

- **The provenance line** — "Read from Album, Artist". The tables the answer
  came from.
- **A plain-English explanation** of what the query did, for someone who does
  not read SQL.

The manual runner only accepts reads. A statement that would change data is
refused — for those, use the approval flow in section 9.

### Checking the query, step by step

Above the SQL is a list called **"How this was worked out"** — the query
broken into plain-language steps:

> 1. Start from the Album table
> 2. Join to the Artist table on the artist
> 3. Count the albums for each artist
> 4. Sort by that count, highest first
> 5. Take the top 10

Each step names one operation and the table or column it acts on. A wall of
SQL forces a non-technical reader to either verify it properly or skip it;
steps let them check the one operation they actually care about. If a step is
not what you meant, say so and the agent will try again.

### The confidence signal

Sometimes the agent's answer carries a **Confidence: medium** or
**Confidence: low** badge. Hover it to see why.

The signal is **High / Medium / Low**, never a percentage, and it is derived
from what actually happened during the run:

| Level | When | Why |
|---|---|---|
| High | The query ran correctly first time | Nothing went wrong. |
| Medium | The answer came from the cache | The question closely matched an earlier one, so the query was not re-derived. |
| Low | The query failed and had to be corrected | The agent got it wrong the first time. Check the steps and the SQL. |

A number like "73% confident" would be worse than useless — the model has no
calibrated probability over its own correctness, and research finds that
numeric confidence that does not track accuracy makes people *more* confident
without making them any better at spotting errors. A label tied to
observable evidence is honest and tells you what to do about it.

---

## 9. Changes to your data: the approval flow

The agent **cannot** change your data on its own. Any statement that would
write, update or delete is stopped before it runs.

**What triggers it:** `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`,
`TRUNCATE`.

**What you see.** Instead of running, the agent returns a card:

> **Delete 12 rows from 'Invoice'?**
> Permanently removes rows from Invoice. This cannot be undone.
>
> | Rows affected | 12 |
> | Table | Invoice |
> | Statement | DELETE |
>
> *12 row(s) in Invoice would be removed. Nothing has been changed yet.*
>
> **Rows that would be affected:**
> [a sample of the affected rows]
>
> [Delete now] [Keep the data]

The **rows affected** count comes from a `SELECT COUNT(*)` with the same
`WHERE` clause, and the sample rows come from a `SELECT` — both read-only,
both inside a transaction that is rolled back. The preview never modifies
anything.

**Then you choose.** **Delete now** executes it. **Keep the data** does
nothing and says so.

The wording follows the established confirmation-dialog conventions: the
title names the object and uses the same verb as the button, the description
states the consequence, the buttons use specific verbs rather than "OK" or
"Yes", and the destructive button is never focused automatically — so a
stray Enter keypress cannot destroy data.

**Two things worth knowing:**

- The check looks at the *structure* of the statement, not just for keywords.
  A read query containing the word `DELETE` inside a string is correctly
  allowed through; a `DELETE` hidden behind a `WITH` clause is still caught.
- A destructive query against a table the agent did not mention in your
  question is still caught. The safety check does not care how the statement
  was phrased.

---

## 10. The schema explorer

The left panel lists every table in the connected database.

- **Search** filters tables and columns as you type.
- **Click a table** to expand its columns and types.
- **Click a column** to ask the agent about that column directly.
- **Double-click a table** to see a sample of its rows.

Each row shows the column count, so you can spot the big tables at a glance.

---

## 11. Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Enter` | Send the question |
| `Shift` + `Enter` | New line in the question box |
| `Ctrl/Cmd` + `K` | Jump to the question box |
| `Ctrl/Cmd` + `B` | Toggle the database explorer |
| `Ctrl/Cmd` + `J` | Toggle the conversation panel |
| `Ctrl/Cmd` + `,` | Open the connection wizard |
| `Esc` | Close the connection wizard |

---

## 12. Accessibility

The interface is built to WCAG 2.2 AA:

- **Contrast.** Every text and interface colour meets the AA contrast
  requirement in both light and dark themes. The chart palette is validated
  for colour-blind separation, not just contrast.
- **Keyboard.** Every control is reachable and operable by keyboard, with a
  visible focus ring. The data table is a real HTML table, so screen readers
  announce row and column headers correctly, and the sort direction is
  announced via `aria-sort`.
- **No colour-only meaning.** Status is always carried by an icon and a label
  as well as a colour. The chart has a table view of the same data beneath
  it.
- **Motion.** Animation is disabled for anyone whose system requests reduced
  motion.
- **Live regions.** New answers and error messages are announced politely
  without stealing focus.

---

## 13. How the agent works

```
                    ┌──────────────────────┐
   your question →  │   Semantic cache     │──hit──→ instant answer
                    └──────────┬───────────┘
                               │ miss
                    ┌──────────▼───────────┐
                    │  Schema retrieval    │  Which tables are relevant?
                    │      (Qdrant)        │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   SQL generation     │  Gemini writes the query
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │    Safe execution    │──destructive──→ ask you
                    └──────────┬───────────┘
                               │ success
                    ┌──────────▼───────────┐
                    │   Answer synthesis   │  Prose + insight + explanation
                    └──────────────────────┘
```

**Schema retrieval.** When you connect, every table's structure is turned into
text, embedded, and stored in Qdrant. Each question retrieves the five most
relevant tables, so the model sees your real column names rather than a
guess. If the vector store is unavailable, the full schema is used instead —
slower, but never wrong.

**Self-healing.** A failed query returns the database's error to the model,
which is asked to fix it. This repeats up to three times. The retries are
shown to you in a collapsed panel, so you can see when the agent had to
correct itself.

**Semantic cache.** Successful answers are stored with their question. A new
question that is more than 95% similar returns the cached answer and re-runs
the cached SQL, so you still see live data. The status bar shows how long the
last answer took, so a cache hit is visible.

**Safety.** Every statement is classified before execution. Read-only
statements run. Mutating statements are intercepted and returned to you for
approval with a preview of their impact.

---

## 14. API reference

All endpoints are JSON over HTTP.

### `POST /connect`

Indexes a database's schema.

```json
{ "tenant_id": "default_tenant", "db_uri": "sqlite:///./chinook.db" }
```

### `POST /schema`

Returns the table and column structure.

```json
{ "success": true, "tables": [{ "name": "Album", "columns": [{ "name": "AlbumId", "type": "INTEGER" }] }] }
```

### `POST /starter_questions`

Returns questions generated from that database's own schema.

```json
{ "success": true, "questions": [{ "question": "How many albums are there?", "table": "Album" }] }
```

### `POST /chat`

Asks a question.

```json
{ "query": "How many albums are there?", "tenant_id": "default_tenant", "db_uri": "sqlite:///./chinook.db" }
```

Returns `simple_answer`, `sql_query`, `execution_result`, `columns`,
`row_count`, `insight`, `sql_explanation`, `chart_type`, `error_traces`,
`cached`, `requires_approval`, `truncated`, `analysis`, `follow_ups` and
`tables_used`.

| Field | What it is |
|---|---|
| `simple_answer` | The prose answer. |
| `sql_query` | The SQL that ran. |
| `execution_result` | The rows, as a list of objects. |
| `columns` | The column names, in order. |
| `row_count` | How many rows came back. |
| `truncated` | True if the server capped the result. |
| `insight` | The headline finding, in plain language. |
| `sql_explanation` | One sentence on what the query did. |
| `chart_type` | `bar`, `line`, `scatter` or `none`. |
| `follow_ups` | Up to three questions to ask next. |
| `tables_used` | The tables the answer came from. |
| `error_traces` | The errors the agent fixed on its own. |
| `cached` | True if the answer came from the semantic cache. |
| `requires_approval` | True if the statement would change data. |
| `analysis` | The statement classification. |

### `POST /preview_sql`

Classifies a statement and estimates its impact **without running it**.

```json
{ "sql": "DELETE FROM Album WHERE AlbumId = 1", "db_uri": "sqlite:///./chinook.db" }
```

### `POST /run_sql`

Runs a read-only statement. Mutating statements are refused.

```json
{ "sql": "SELECT * FROM Album LIMIT 10", "db_uri": "sqlite:///./chinook.db", "limit": 200 }
```

### `POST /execute_approved`

Runs a statement the user has explicitly approved.

```json
{ "sql": "DELETE FROM Album WHERE AlbumId = 1", "tenant_id": "default_tenant", "db_uri": "sqlite:///./chinook.db" }
```

### `POST /upload_db`

Uploads a SQLite file. Returns `{ "success": true, "db_uri": "sqlite:////tmp/...", "filename": "..." }`.

---

## 15. Architecture

```
static/
  index.html            the shell
  css/
    tokens.css          colours, type, spacing - the whole design system
    base.css            reset and shared controls
    layout.css          the application shell
    components.css      chat, grid, chart, wizard, modal
  js/
    app.js              entry point - wires everything together
    state.js            the observable store
    api.js              every network call, one place for error handling
    chat.js             the conversation
    datagrid.js         the result table
    chart.js            chart type selection and rendering
    explorer.js         the schema tree
    wizard.js           the connection wizard
    ui.js               DOM helpers and the icon set
    toast.js            notifications
    icons-init.js       fills the icon-only buttons

agent.py                the LangGraph state machine
tools.py                SQL execution, the safety gate, schema reading
sql_analysis.py         statement classification and impact preview
starter_questions.py    schema-derived starter questions
embeddings.py           the hosted encoder, with a local fallback
vector_store.py         Qdrant: schema index and semantic cache
mock_llm.py             deterministic responses, for testing and demos
app.py                  the FastAPI application
```

**Why vanilla ES modules and not React:** the app ships without a build step.
`Dockerfile` copies the source and runs uvicorn. There is no `node_modules`, no
bundler, and no chance of a deploy failing on a toolchain version. The
modules are small and separated by responsibility, so the trade is clean.

**Why the design tokens are separate:** every colour, size and duration
resolves to a token in `tokens.css`. Both themes are defined there, so a
component never hard-codes a colour and the light and dark themes cannot
drift apart.

---

## 16. Testing

```bash
pytest tests/ -v          # the Python suite
node tests/ui_smoke.js    # the frontend suite
```

The Python suite covers the safety gate (destructive statements are
intercepted), the statement classifier, the impact preview, the read path,
the FastAPI endpoints, and the agent state machine.

The frontend suite runs the real modules against a stubbed DOM and checks
the data grid's sorting, filtering and paging, the chart planner, the chat
message rendering, the SQL editor, and the connection wizard's URI building.

**Two ways to run the tests.**

```bash
# 1. Deterministic - no API key, no network, no cost.
MOCK_LLM=1 pytest tests/ -v

# 2. Against the real model. Costs money and is slow, so it is opt-in.
RUN_MODEL_TESTS=1 pytest tests/ -v
```

The tests that call the real model are **skipped** unless
`RUN_MODEL_TESTS=1` is set. Everything else always runs.

**MOCK_LLM=1** replaces the model call with a deterministic stand-in. Every
other part of the app runs unchanged — the same nodes, the same safety gate,
the same response shape. It is the quickest way to exercise the interface
without an API key, and it is what makes the test suite deterministic.

**The suite needs a working Qdrant instance** for the semantic cache to
persist between runs. Without one, the vector store falls back to an
in-memory store, which works but does not survive a restart.

```bash
pytest tests/test_backend.py -v      # API and safety gate
pytest tests/test_agent.py -v        # the agent loop
node tests/ui_smoke.js               # the frontend
```

**No API key at all?** The app still runs. The hosted embedding endpoint and
the vector store both fall back to local implementations, and the model falls
back to the mock when `MOCK_LLM=1` is set. See section 17.

**Checking the interface by hand?** See [QA_CHECKLIST.md](QA_CHECKLIST.md) — a
walkthrough for the things the automated tests cannot check, which is
appearance: layout, contrast, spacing, and the visual polish.

**The research behind the interface design** — what was adopted from
Databricks Genie, Snowflake, BigQuery and the human-AI interaction
literature, and what was deliberately left out — is recorded in
[UI_GUIDE.md](UI_GUIDE.md).

---

## 17. Troubleshooting

**"Could not reach the server."**
The backend is not running, or the page was opened as a file rather than
through the server. Start uvicorn and use `http://localhost:8000`.

**"Could not connect."**
Check the host, port, username, password and database name. A Postgres host
that is reachable from your laptop may not be reachable from the server
running the app.

**The agent answers, but the SQL looks wrong.**
The question was ambiguous. Look at the SQL to see which column it chose, and
rephrase to name that column explicitly.

**The chart did not appear.**
Charts need a category and a measure, or a date and a measure. A table of
names has neither, so the table is shown on its own.

**"No schema available."**
The database was not connected, or the connection dropped. Reconnect from the
connection chip.

**The app is slow.**
The first question on a new database pays for the schema index. Questions
after that are faster, and repeated questions are faster still because of the
semantic cache.

**Qdrant errors in the logs.**
The vector store falls back to an in-memory store and the app keeps working.
The schema is no longer filtered by relevance, so the model sees every table.

**"The hosted encoder is unavailable" or a 402 from Hugging Face.**
The hosted embedding endpoint needs credits. The app falls back to a local
encoder, which works on keyword match — good enough for schema retrieval and
the semantic cache, and it needs no network.

**"You exceeded your current quota" from Gemini.**
The model provider's quota is exhausted. Wait for the quota to reset, or
point `MODEL` at a different model. For interface work with no quota, set
`MOCK_LLM=1` — the app then runs end to end against deterministic responses.

**The app runs but the answers are poor.**
Check that the model is reachable at all, then check the schema was indexed.
Reconnect from the connection chip, and watch the server log for
`Loaded N table schemas into Qdrant`.

**A follow-up question gives a different answer than the first one.**
The agent answers each question independently, using only the question text —
it does not carry the conversation forward. This is a deliberate choice: it
keeps every answer reproducible and checkable. Name the columns you mean.

---

## 18. Deployment

### Docker

```bash
docker build -t sql-agent .
docker run -p 8000:8000 --env-file .env sql-agent
```

### Render

Build command `pip install -r requirements.txt`, start command
`uvicorn app:app --host 0.0.0.0 --port $PORT`. The Dockerfile already does
this.

### Notes for production

- Set `FRONTEND_URL` to your frontend's origin instead of leaving CORS open.
- Keep `GEMINI_API_KEY`, `QDRANT_API_KEY` and any database password in your
  platform's secret store, never in the image.
- Put the app behind a reverse proxy with TLS.
- The `/upload_db` endpoint writes uploaded files to `/tmp/sql_agent_uploads`.
  Files are written under their sanitised base name, but the endpoint has no
  authentication — add one before exposing it publicly.
- Read-only database credentials are enough for most uses. Give the agent
  write access only if you intend to use the approval flow.

---

## License

MIT — see the [LICENSE](LICENSE) file.
