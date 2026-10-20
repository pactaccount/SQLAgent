# Manual QA checklist

A walkthrough for checking the interface by hand. The automated suites
(`pytest tests/` and `node tests/ui_smoke.js`) verify behaviour, not
appearance — so the things listed here that concern **layout, contrast,
spacing, and visual polish** are the ones no test can catch.

## How to run it

```bash
# 1. Start the app against the bundled sample database.
MOCK_LLM=1 uvicorn app:app --reload
#    Then open http://127.0.0.1:8000

# 2. Connect the sample database in the wizard:
#    "A database file on my computer" -> path `chinook.db`
```

> **Mock mode.** `MOCK_LLM=1` replaces the model with deterministic canned
> answers, so responses are fixed and repeatable. That is what you want for
> checking the interface. To check the real model, start the server without
> it.

**The skipped Python tests are the model-dependent ones.** They only run with
`RUN_MODEL_TESTS=1`. That is intentional, not a gap.

---

## 1. First impression (before connecting anything)

- [ ] An **AI notice** bar appears at the very top: "Answers here are written by
      an AI model, which can misread a question…"
- [ ] The notice is above the whole app, full width, and readable in both themes.
- [ ] Three panels: **Database** (left), **SQL + Results** (centre), **Ask**
      (right).
- [ ] Top bar shows "Not connected" with a grey dot on the connection chip.
- [ ] Status bar (bottom) shows "Not connected".

## 2. The connection wizard

- [ ] Click **Connect a database**. A 3-step modal opens.
- [ ] Step 1 shows four options with plain-language descriptions
      ("A database file on my computer", "PostgreSQL", "MySQL", "Snowflake").
- [ ] The step indicator shows 1 → 2 → 3.
- [ ] Click **A database file on my computer** → Continue.
- [ ] Step 2 shows a **drop zone**. "Continue" is **disabled** (nothing filled in).
- [ ] Type a path in "Or enter a file path" → Continue becomes enabled.
- [ ] Type `chinook.db` (relative to the server's working dir) and continue.
- [ ] Step 3 summarises what you entered. Click **Connect**.
- [ ] The modal closes, the chip turns **green** and reads "sqlite" plus the
      workspace name you set, and the explorer fills with tables.
- [ ] Reopen the wizard → your previous type and tenant are remembered.

## 3. The schema explorer (left panel)

- [ ] Tables are listed with a column count (Album 11, Artist 5, …).
- [ ] Click a table → it expands to show columns and types.
- [ ] Type in the search box → it filters tables and columns live.
- [ ] Search for something that does not exist → "No matches", not a blank panel.
- [ ] Click a **column** → it asks the agent about that column.
- [ ] Double-click a **table** → it asks for a sample of its rows.

## 4. Asking a question (the main flow)

Click a starter question, or type your own.

- [ ] The question appears as a bubble on the right.
- [ ] A typing indicator shows while it works.
- [ ] The answer arrives with: **status badges**, the **answer text**,
      **"What stands out"**, **"How this was worked out"** (numbered steps),
      a collapsed **"View the SQL that was run"**, **"Try asking"** chips, and
      **Copy answer / Ask again**.
- [ ] The **AI notice disappears** after the first question.
- [ ] The centre panel fills with the SQL and the result table.
- [ ] The status bar shows the row count and the elapsed time.
- [ ] The answer does **not** scroll the view away if you had scrolled up
      (send a second question after scrolling up — your position should hold).

## 5. The step breakdown

- [ ] "How this was worked out" shows 2–5 numbered plain-language steps.
- [ ] No step contains SQL keywords or uppercase table names.
- [ ] Each step names a table or column.
- [ ] It reads as an explanation of *the query*, not of the model's thinking.

## 6. The SQL disclosure

- [ ] Click "View the SQL that was run" → it expands.
- [ ] It shows the **provenance line** ("Read from Artist, Album").
- [ ] It shows the **plain-English explanation**.
- [ ] The SQL is in an **editable textarea**.
- [ ] **Edit it** (e.g. change `LIMIT 10` to `LIMIT 3`) → click **Run this SQL**
      → the results table updates to 3 rows.
- [ ] **Copy SQL** → paste into a text editor to confirm it copied.
- [ ] Click a **"Try asking"** chip → it runs as a new question.

## 7. The result table

- [ ] Numbers are right-aligned with thousands separators.
- [ ] `NULL` appears in italics.
- [ ] Click a column header → sorts ascending. Click again → descending. Click a
      third time → back to unsorted.
- [ ] The sort arrow appears on the sorted column only.
- [ ] Type in **Filter rows** → the table narrows and the count updates to
      "N of M rows".
- [ ] **CSV** downloads a file; open it — headers and rows should match.
- [ ] **JSON** downloads a file; open it — should be a JSON array of objects.
- [ ] With a long result, **First / Previous / Next** appear and work.

## 8. The chart

- [ ] A chart appears above the table when the data suits one (category +
      measure → bars; date + measure → line).
- [ ] **Bars / Line** buttons switch the chart type.
- [ ] No chart appears for a plain list of names.
- [ ] Hovering a bar shows the exact value.
- [ ] The chart **does not replace** the table — the table is always there.
- [ ] Switching to light theme → the chart redraws with correct colours.

## 9. The safety flow (most important)

Ask: **"Delete all albums"**

- [ ] The query is **not** executed.
- [ ] An approval card appears: the title names the table and row count
      ("Delete 12 rows from 'Album'?"), the description states the consequence
      and says "This cannot be undone".
- [ ] The impact list shows **Rows affected**, **Table**, **Statement**.
- [ ] A sample of the affected rows is shown.
- [ ] The buttons read **"Delete now"** and **"Keep the data"** — not "OK"/
      "Cancel".
- [ ] **Press Enter without clicking** — nothing should happen. The destructive
      button must not be pre-focused.
- [ ] Click **Keep the data** → a toast says nothing was changed.
- [ ] Run it again, click **Delete now** → it executes, and the row count
      changes.
- [ ] Check the database is really changed:
      `sqlite3 chinook.db "select count(*) from Album"` (or ask "how many albums")
      → the number is lower.

## 10. Theme, panels, tabs

- [ ] The ☀/☾ button in the top bar switches theme. **Both themes are readable**
      — check text contrast, borders, and the chart.
- [ ] The rail icons toggle the left and right panels; the active one is
      highlighted.
- [ ] `+` on the tab bar opens a new query tab. Tabs are independent.
- [ ] `×` on a tab closes it (the last tab cannot be closed).
- [ ] Panels can be dragged to resize. Dragging past the edge stops cleanly.
- [ ] The theme and panel state **survive a page reload**.

## 11. Keyboard

- [ ] `Ctrl/Cmd + K` jumps to the question box.
- [ ] `Ctrl/Cmd + B` toggles the explorer, `Ctrl/Cmd + J` the conversation.
- [ ] `Ctrl/Cmd + ,` opens the connection wizard.
- [ ] `Esc` closes the wizard.
- [ ] `Enter` sends, `Shift+Enter` makes a new line.
- [ ] Tab through the interface — every control gets a **visible focus ring**.

## 12. Accessibility

- [ ] Turn on a screen reader (VoiceOver `Cmd+F5`). The answer is announced.
- [ ] The result table announces the column headers with each cell.
- [ ] Sorting is announced (ascending / descending).
- [ ] The connection chip and the status bar read sensibly.
- [ ] Nothing important is conveyed by colour alone — the approval card, the
      badges and the confidence badge all have an icon and a word.
- [ ] macOS → Accessibility → Display → Increase contrast, and
      **Reduce motion** — the interface still works.

## 13. Export and errors

- [ ] The download icon in the "Ask" panel header exports the conversation as a
      `.txt` file. Open it — it should read as a readable transcript.
- [ ] Stop the server, then ask a question → a friendly error appears in the
      chat, not a raw stack trace. Restart the server and try again.

---

## Reporting back

For anything that fails, note: **what you did**, **what you expected**, and
**what happened** (a screenshot helps). If something looks wrong but you are
not sure, that is still worth reporting — visual/layout issues are exactly
what the automated tests cannot catch, since they assert behaviour, not
appearance.
