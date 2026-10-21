# Getting started

A short, practical guide to getting value out of the SQL Agent. Work through
it in order the first time — it takes about ten minutes and leaves you with a
working setup, your first answer, and a sense of what the tool can and cannot
do.

If you would rather jump straight in, the [Quick start](#quick-start) below
gets you running in about two minutes.

---

## Contents

1. [What this tool is](#1-what-this-tool-is)
2. [Quick start](#2-quick-start)
3. [Step 1 — Install and run it](#3-step-1--install-and-run-it)
4. [Step 2 — Connect a database](#4-step-2--connect-a-database)
5. [Step 3 — Ask your first question](#5-step-3--ask-your-first-question)
6. [Step 4 — Read the answer properly](#6-step-4--read-the-answer-properly)
7. [Working with query tabs](#7-working-with-query-tabs)
8. [Asking better questions](#8-asking-better-questions)
9. [Working with the results](#9-working-with-the-results)
10. [When the agent changes your data](#10-when-the-agent-changes-your-data)
11. [Common problems](#11-common-problems)
12. [Reference — keyboard shortcuts and the panels](#12-reference--keyboard-shortcuts-and-the-panels)

---

## 1. What this tool is

You ask a question in ordinary English. The agent finds the right tables in
your database, writes SQL, runs it, and shows you three things:

- **The answer** — a sentence.
- **The table** — your data, sortable and exportable.
- **The query** — the SQL it ran, so you can check it.

The important part is that last one. The agent is not a black box: every
answer comes with the query that produced it, broken into plain-language
steps, and you can edit the query and re-run it. If the agent misunderstood
you, you fix it rather than arguing with it.

**What it is not:** it does not write reports, it does not schedule anything,
and it does not connect to a dashboard. It answers questions about one
database at a time.

---

## 2. Quick start

```bash
git clone https://github.com/pactaccount/SQLAgent.git
cd SQLAgent

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.template .env
# Add your GEMINI_API_KEY to .env

uvicorn app:app --reload
```

Open **http://127.0.0.1:8000**, click **Connect a database**, choose
**"A database file on my computer"**, and point it at the bundled
`chinook.db`. Then click one of the suggested questions.

If you have no API key, run it with `MOCK_LLM=1 uvicorn app:app --reload` and
the app works end to end with fixed, canned answers — enough to explore the
interface.

---

## 3. Step 1 — Install and run it

### What you need

| | |
|---|---|
| **Python** | 3.9 or newer |
| **A Gemini API key** | From [Google AI Studio](https://aistudio.google.com/) — put it in `.env` as `GEMINI_API_KEY` |
| **A database** | A SQLite file, or a PostgreSQL / MySQL / Snowflake connection |

The optional extras — a Qdrant Cloud cluster and a Hugging Face token — make
schema retrieval sharper and enable the semantic cache. **You do not need
them.** Without them the app falls back to local implementations and works
normally; it just reads more of your schema into the prompt.

### Start it

```bash
source venv/bin/activate
uvicorn app:app --reload
```

You should see `Uvicorn running on http://127.0.0.1:8000`. Open that URL.

### Check it works

```bash
# In another terminal
curl -s http://127.0.0.1:8000/ | head -5
```

---

## 4. Step 2 — Connect a database

Click **Connect a database** in the top right, or the chip in the top bar. The
wizard has three steps.

### Choosing the kind of database

| Choose | If your data is… |
|---|---|
| **A database file on my computer** | A single `.db` / `.sqlite` file. Easiest way to start. |
| **PostgreSQL** | A hosted Postgres database. |
| **MySQL** | A hosted MySQL database. |
| **Snowflake** | A Snowflake warehouse. |

### Adding the details

**For a file:** drag it onto the drop zone, or click to browse. You can also
type a path if the file is already on the server's machine. The bundled
`chinook.db` is a music-store sample with 11 tables — a good place to learn
the interface.

**For a server database:** you need the host, port, username, password and
database name. The port is filled in for you (5432 for Postgres, 3306 for
MySQL). The **Continue** button stays disabled until the required fields are
filled in, so you cannot get past a missing password by accident.

**Workspace name** is optional. It keeps one database's schema separate from
another's on the same server. Leave it blank unless you were told otherwise.

### What happens when you connect

The app reads your table structure and indexes it. That takes a moment on a
large database. When it finishes:

- The chip in the top bar turns **green** and shows the database type.
- The **Database** panel on the left fills with your tables.
- The conversation offers **suggested questions**, generated from your own
  schema. They are guaranteed to be answerable, because they are built from
  tables and columns that actually exist.

**Connecting to a different database clears your conversations**, because
answers from one database do not describe another.

---

## 5. Step 3 — Ask your first question

Click one of the suggested questions, or type your own.

Here is a question that shows the tool off:

> **Which artist has the most albums?**

You get back:

1. **The answer** — "Iron Maiden have the most albums, with 8."
2. **What stands out** — the single most interesting fact in the data.
3. **How this was worked out** — the query as numbered plain-language steps.
4. **The SQL** — collapsed, one click away.
5. **Try asking** — follow-up questions you could ask next.

The results table appears in the centre panel with a chart above it, and the
status bar at the bottom shows how long it took.

### Your first useful question

The best first question is one that names a **measure** and a **grouping**:

> "What is the total revenue for each billing country?"

rather than

> "Show me the data"

The second is a request the agent has to interpret. The first tells it
exactly what to compute, and you get a much more reliable answer.

---

## 6. Step 4 — Read the answer properly

The agent can be wrong. It is reading your question and guessing which
columns you meant. The interface gives you three ways to check.

### Read the steps

> 1. Start from the Album table
> 2. Join to the Artist table on the artist
> 3. Count the albums for each artist
> 4. Sort by that count, highest first
> 5. Take the top 10

Each step names one operation. If a step is not what you meant, that is your
cue to rephrase.

### Read the SQL

Click **View the SQL that was run**. The provenance line tells you which
tables were read. The plain-English line says what the query did.

### Fix it yourself

The SQL is **editable**. Change it and press **Run this SQL** — the results
update immediately, without going back to the chat. This is the fastest way
to correct a misread question: change the column, add a filter, change the
limit.

### Read the confidence badge

If the answer carries a **Confidence: medium** or **Confidence: low** badge,
hover it to see why:

| Level | Means | What to do |
|---|---|---|
| **High** | The query ran correctly first time. | Read it if it matters. |
| **Medium** | The answer came from the cache, so the question closely matched an earlier one. | Fine if it is the same question. |
| **Low** | The query failed and had to be corrected. | Check the steps and the SQL carefully. |

---

## 7. Working with query tabs

Each tab is an **independent query session**. It keeps its own conversation,
its own SQL, and its own results.

| Action | How |
|---|---|
| **Open a new tab** | Click **+** at the right of the tab bar. |
| **Switch tabs** | Click the tab. Your conversation comes back exactly as you left it. |
| **Close a tab** | Click the **×** on the tab. |
| **Rename** | The tab takes the name of your first question, so you can tell them apart. |

### Using tabs well

- **One question per tab.** If you are chasing a second question, open a new
  tab rather than asking a follow-up in the same one. You keep both lines of
  enquiry side by side.
- **Tabs are temporary.** They live in the browser tab you have open. Closing
  the browser tab loses them — export the conversation first if you want to
  keep it (see below).
- **The last tab cannot be closed.** There has to be somewhere to type the
  next question. The **×** is still there, but it will tell you why it did
  nothing.

### Exporting a conversation

The download icon in the **Ask** panel header saves the current conversation
as a text file — useful for pasting into a ticket, a document, or an email.

---

## 8. Asking better questions

### The pattern that works

> **[What to measure] for each [what to group by]**, [any limit or filter].

Examples:

| Question | Why it works |
|---|---|
| "What is the total revenue for each billing country?" | Names the measure and the grouping. |
| "Which 10 customers have spent the most?" | Names the measure, the grouping and the limit. |
| "How has the average track length changed by year?" | Names the measure and the time axis. |
| "List the distinct genres in the database." | A simple listing, no ambiguity. |

### What to avoid

| Avoid | Why | Instead |
|---|---|---|
| "Show me the data" | Nothing to compute. | "List the first 20 albums." |
| "Which one is the best?" | "Best" is undefined. | "Which artist has the most albums?" |
| "Sales" | Ambiguous — total, count, or average? | "What is the total revenue by month?" |

### Use the explorer

The **Database** panel on the left lists every table and column. If you are
not sure what a column is called, look — or click the column to ask the
agent about it directly. Naming the real column name is the single most
reliable way to get the query you want.

### Ask one question at a time

The agent answers the question it was asked. It does not carry a conversation
forward, so "now for 2020" will not work on its own — say "What is the total
revenue for each country in 2020?"

---

## 9. Working with the results

### The chart

A chart appears above the table **only** when the data suits one — a category
against a measure, or a date against a measure. A plain list of names gets
no chart, because a chart would add nothing.

- **Bars / Line** switches between the two.
- Hover any mark for the exact value.
- Every value is also in the table below, so nothing is only reachable by hovering.

### The table

| Control | What it does |
|---|---|
| **Column header** | Click to sort. Click again for descending, a third time to clear. `NULL` always sorts last. |
| **Filter rows** | Filters across all columns as you type. |
| **CSV / JSON** | Downloads the current result set. |
| **First / Previous / Next** | Pages through long results, 100 rows at a time. |

Numbers are right-aligned with thousands separators. `NULL` is italic, so an
empty value is never confused with the text "NULL". A long cell is truncated
with an ellipsis — hover it to see all of it.

### A note on large results

The agent returns up to 5,000 rows. If your question matches more, the table
says so and the export still contains everything that was returned. For a
genuinely large export, use the **CSV** button and page through, or write
the query yourself in the SQL panel.

---

## 10. When the agent changes your data

**The agent cannot change your data without your approval.** Any statement
that would write, update or delete is stopped before it runs.

Ask it to delete something and you get a card like this:

> **Delete 12 rows from 'Invoice'?**
> Permanently removes rows from Invoice. This cannot be undone.
>
> | Rows affected | 12 |
> | Table | Invoice |
> | Statement | DELETE |
>
> **Rows that would be affected:**
> [a sample of the affected rows]
>
> **[Delete now]** **[Keep the data]**

- **Rows affected** is an exact count, computed with a `SELECT COUNT(*)` and
  the same `WHERE` clause.
- **The sample** shows you what would actually be touched.
- Both are read-only, inside a transaction that is rolled back. **The preview
  itself changes nothing.**
- **Delete now** runs it. **Keep the data** does nothing.

The destructive-button check is structural, not a keyword scan. A read query
that happens to contain the word `DELETE` in a string is allowed through; a
write hidden behind a `WITH` clause is still caught.

**Give read-only database credentials** unless you intend to use this flow.
The tool works perfectly well as a reader.

---

## 11. Common problems

**"Could not reach the server."**
The backend is not running, or the page was opened as a file rather than
through the server. Start uvicorn and use `http://127.0.0.1:8000`.

**"Could not connect."**
Check the host, port, username, password and database name. A database
reachable from your laptop may not be reachable from the machine running the
app.

**The agent answers, but the SQL looks wrong.**
The question was ambiguous. Look at the steps to see which column it chose,
then either rephrase to name that column explicitly, or edit the SQL in the
disclosure and re-run it.

**The answer is right but the number looks off.**
Check the filter. The agent may have applied a filter you did not intend.
Read the `WHERE` clause in the SQL.

**"You exceeded your current quota" / a 429 from Gemini.**
Your model provider's quota is exhausted. Wait for it to reset, or set
`MODEL` to a different model. To explore the interface with no quota, run
with `MOCK_LLM=1`.

**"No schema available."**
The database was not connected, or the connection dropped. Reconnect from the
chip in the top bar.

**It is slow.**
The first question on a new database pays for indexing the schema. Later
questions are faster, and repeated ones are faster still, because of the
semantic cache.

**The chart did not appear.**
Charts need a category and a measure, or a date and a measure. A table of
names has neither, so the table is shown on its own.

---

## 12. Reference — keyboard shortcuts and the panels

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Enter` | Send the question |
| `Shift` + `Enter` | New line in the question box |
| `Ctrl/Cmd` + `K` | Jump to the question box |
| `Ctrl/Cmd` + `B` | Toggle the database explorer |
| `Ctrl/Cmd` + `J` | Toggle the conversation panel |
| `Ctrl/Cmd` + `,` | Open the connection wizard |
| `Esc` | Close the connection wizard |

### The three panels

**Database (left)** — every table and column. Search it, expand a table,
click a column to ask about it, or double-click a table to see a sample of
its rows.

**SQL and results (centre)** — the tab bar across the top, then the SQL the
agent ran, then the chart and the result table.

**Ask (right)** — the conversation, and the question box at the bottom.

### The status bar

Left: the connection state. Middle: the row count of the last result. Right:
how long the last question took.

---

## Where to go next

- **[QA_CHECKLIST.md](QA_CHECKLIST.md)** — a walkthrough for checking every
  feature by hand, including accessibility.
- **[UI_GUIDE.md](UI_GUIDE.md)** — the research behind the interface design:
  what was taken from Databricks Genie, Snowflake, BigQuery and the
  human-AI interaction literature, and what was deliberately left out.
- **[IEEE_Documentation.md](IEEE_Documentation.md)** — the system
  architecture, the safety design, and the evaluation results.
