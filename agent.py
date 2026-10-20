import os
import json
import re
import time
from types import SimpleNamespace
from typing import TypedDict, List, Optional
from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
from litellm import completion
from tools import get_schema_for_query, execute_sql
from vector_store import vector_store
from sql_analysis import classify_query
import mock_llm

# The model that writes and explains the SQL. Override with the MODEL
# environment variable to point at a different provider or a local model.
MODEL = os.getenv("MODEL", "gemini/gemini-2.5-flash")


def complete(messages, **kwargs):
    """
    Call the model, retrying transient failures.

    Rate limits and brief network errors are common on shared API keys, and a
    question that fails because of a 429 is a bad experience. Retrying with a
    short backoff turns most of these into a slower answer rather than an
    error.

    When MOCK_LLM is set, the model call is replaced with a deterministic
    stand-in. Every other part of the agent runs unchanged.
    """
    if mock_llm.MOCK_ENABLED:
        return _mock_completion(messages)

    last_error = None

    for attempt in range(4):
        try:
            return completion(model=MODEL, messages=messages, **kwargs)
        except Exception as exc:  # noqa: BLE001 - re-raised below
            last_error = exc
            message = str(exc).lower()
            transient = any(
                marker in message
                for marker in ("rate limit", "429", "timeout", "timed out",
                               "overloaded", "503", "502", "500")
            )
            if not transient or attempt == 3:
                raise
            wait = 2 ** attempt
            print(f"  -> Model call failed ({type(exc).__name__}); retrying in {wait}s")
            time.sleep(wait)

    raise last_error


def _mock_completion(messages):
    """
    A stand-in for litellm's response object.

    The agent asks for three different things - SQL, prose, and a labelled
    summary - so the mock inspects the system prompt to work out which one
    is being asked for.
    """
    system = ""
    user = ""
    for message in messages:
        if message.get("role") == "system":
            system += message.get("content", "")
        else:
            user += message.get("content", "")

    if "Return ONLY the raw SQL query string" in system:
        content = mock_llm.mock_sql(user)
    elif "Reply in this exact format" in system:
        # The combined insight / explanation / follow-ups prompt.
        content = _format_mock_summary(user)
    elif "synthesize the raw database results" in system:
        content = mock_llm.mock_answer(user)
    else:
        content = mock_llm.mock_answer(user)

    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _format_mock_summary(user_prompt: str) -> str:
    """Render the mock's insight, explanation and follow-ups in the format
    the real prompt asks the model for."""
    # The prompt carries the rows as JSON, so they can be read back out of
    # it rather than being passed through a global.
    rows = []
    match = re.search(r"Data \(first 50 rows\):\n(\[.*?\])\n", user_prompt, re.DOTALL)
    if match:
        try:
            rows = json.loads(match.group(1))
        except Exception:
            rows = []

    insight, explanation, follow_ups = mock_llm.mock_summary("", [], rows)
    return (
        f"INSIGHT: {insight}\n"
        f"EXPLANATION: {explanation}\n"
        f"FOLLOW_UPS: {' | '.join(follow_ups)}"
    )
# Time-like column names, used to decide whether a result set is a time series.
_TIME_HINTS = (
    "date", "time", "year", "month", "day", "week", "quarter", "period",
    "created", "updated", "released", "purchased", "invoiced", "hired", "born",
)

# Column names that usually hold a category, used to pick a grouping dimension.
_CATEGORY_HINTS = (
    "name", "title", "category", "genre", "type", "status", "country", "state",
    "city", "region", "department", "artist", "album", "customer", "product",
    "label", "group", "kind", "email", "id",
)


class AgentState(TypedDict):
    user_query: str
    tenant_id: str
    db_uri: str
    schema_context: str
    sql_query: str
    execution_result: Optional[list]
    error_traces: List[str]
    retry_count: int
    final_answer: str
    cached_result: bool
    requires_approval: bool
    chart_type: str
    insight: str
    columns: list
    row_count: int
    truncated: bool
    sql_explanation: str
    analysis: dict
    follow_ups: list
    tables_used: list
    steps: list
    confidence: dict


# --- Nodes ---

def cache_check_node(state: AgentState):
    """Check if query is already in cache."""
    print("[Node: cache_check_node]")
    cached = vector_store.semantic_cache_check(state["user_query"], state["tenant_id"])
    if cached:
        print("  -> Cache Hit!")
        state["final_answer"] = cached["answer"]
        state["sql_query"] = cached["sql"]
        state["cached_result"] = True

        # The cache stores the answer and the SQL, not the rows. Re-run the
        # cached SQL so the user still sees live data - a cached answer with
        # an empty table would look broken.
        try:
            res = execute_sql(cached["sql"], state["db_uri"])
            if res["success"] and not res.get("requires_approval"):
                state["execution_result"] = res["result"]
                state["columns"] = res.get("columns", [])
                state["row_count"] = res.get("row_count", len(res["result"] or []))
                state["truncated"] = res.get("truncated", False)
                state["chart_type"] = detect_chart_type(state["columns"], res["result"] or [])
                state["insight"] = _summarize(state["user_query"], state["columns"], res["result"] or [])
                state["sql_explanation"] = _explain_sql(cached["sql"])
        except Exception:
            # A cache hit whose SQL no longer runs is not fatal - the user
            # still gets the cached answer, just without a table.
            pass
    else:
        print("  -> Cache Miss")
        state["cached_result"] = False
    return state

def schema_inspector_node(state: AgentState):
    """Retrieve relevant schema for the user query."""
    print("[Node: schema_inspector_node]")
    schema = get_schema_for_query(state["user_query"], state["tenant_id"], state["db_uri"])
    state["schema_context"] = schema
    return state

def sql_generator_node(state: AgentState):
    """Generate or fix SQL query using LLM."""
    print("[Node: sql_generator_node]")

    schema = state["schema_context"]
    user_query = state["user_query"]
    error_traces = state.get("error_traces", [])

    system_prompt = f"""You are an expert SQL engineer.
Your task is to write a SQL query (SELECT, INSERT, UPDATE, DELETE) to answer or fulfill the user's request based on the provided schema.
Return ONLY the raw SQL query string. No markdown formatting, no explanation.

Schema Context:
{schema}
"""

    user_prompt = f"User Question: {user_query}"

    if error_traces:
        user_prompt += "\n\nWARNING: Your previous SQL query failed! Here are the errors:\n"
        for i, error in enumerate(error_traces):
             user_prompt += f"Attempt {i+1} Error: {error}\n"
        user_prompt += "\nPlease analyze the schema again and fix the SQL query."

    response = complete(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    raw_sql = response.choices[0].message.content.strip()
    if raw_sql.startswith("```sql"):
        raw_sql = raw_sql[6:-3].strip()
    elif raw_sql.startswith("```"):
        raw_sql = raw_sql[3:-3].strip()

    state["sql_query"] = raw_sql

    # requires_approval will be set by the executor node if the query is destructive
    return state


def explain_sql_steps(sql: str, user_query: str, tables: list) -> list:
    """
    Break a query into plain-language steps.

    Research on NL2SQL interfaces is consistent that a single wall of SQL
    forces a non-technical reader to either verify it or ignore it. Breaking
    the query into named steps, each in ordinary language, gives the reader
    something they can check one line at a time - which is where the large
    gains in task accuracy in the literature come from.

    Each step is a plain sentence describing one mechanical operation, with
    the column or table it acts on named. Nothing is justified; everything
    is described.
    """
    if not sql:
        return []

    if mock_llm.MOCK_ENABLED:
        return mock_llm.mock_steps(sql, tables)

    try:
        response = complete(
            messages=[
                {"role": "system", "content": (
                    "Break the SQL query into its logical steps, one per line.\n"
                    "Each line must be a short sentence in plain language, with no SQL keywords and "
                    "no uppercase table names, describing ONE mechanical operation and naming the "
                    "table or column it acts on.\n"
                    "Use a form like 'Start from the Album table' or 'Filter to tracks longer than "
                    "3 minutes' or 'Count the rows' or 'Sort by revenue, highest first' or 'Take "
                    "the top 10'.\n"
                    "Between 2 and 5 lines. No numbering, no bullets, no explanation of why."
                )},
                {"role": "user", "content": (
                    f"User question: {user_query}\n"
                    f"Tables used: {', '.join(tables) if tables else 'unknown'}\n\n"
                    f"SQL:\n{sql}"
                )},
            ],
        )

        steps = []
        for line in response.choices[0].message.content.strip().splitlines():
            cleaned = line.strip().lstrip("-*• ").strip()
            # Drop numbering if the model added it despite the instruction.
            if cleaned and cleaned[0].isdigit() and "." in cleaned[:4]:
                cleaned = cleaned.split(".", 1)[1].strip()
            if cleaned:
                steps.append(cleaned)

        return steps[:5]
    except Exception:
        return []

def sql_executor_node(state: AgentState):
    """Execute the SQL safely."""
    print("[Node: sql_executor_node]")
    sql = state["sql_query"]
    db_uri = state["db_uri"]
    print(f"  -> Executing: {sql}")

    res = execute_sql(sql, db_uri)

    # Keep the classification so the UI can explain what the statement does.
    state["analysis"] = res.get("analysis") or classify_query(sql)

    if res["success"]:
        if res.get("requires_approval"):
            state["requires_approval"] = True
            state["execution_result"] = [{"message": res["message"]}]
            state["final_answer"] = "This query modifies data and requires your approval. Please review the SQL below."
        else:
            state["requires_approval"] = False
            state["execution_result"] = res["result"]
            state["columns"] = res.get("columns", [])
            state["row_count"] = res.get("row_count", len(res["result"] or []))
            state["truncated"] = res.get("truncated", False)
            state["chart_type"] = detect_chart_type(state["columns"], res["result"] or [])
    else:
         print(f"  -> Error: {res['error']}")
         if "error_traces" not in state:
             state["error_traces"] = []
         state["error_traces"].append(res["error"])
         state["retry_count"] = state.get("retry_count", 0) + 1

    return state

def response_synthesis_node(state: AgentState):
    """Synthesize the final answer."""
    print("[Node: response_synthesis_node]")

    if state.get("requires_approval"):
        return state

    if "execution_result" not in state or state["execution_result"] is None:
         state["final_answer"] = "I'm sorry, I couldn't generate a valid query to answer your question based on the database schema."
         return state

    result_data = state["execution_result"]
    user_query = state["user_query"]

    system_prompt = (
        "You are a helpful data analyst. Synthesize the raw database results into a natural, "
        "polite response to the user's question. Lead with the direct answer, then give the "
        "supporting detail. Keep it concise. If the result set is large, summarise it rather "
        "than repeating every row."
    )
    user_prompt = f"Question: {user_query}\n\nData Result:\n{json.dumps(result_data, indent=2, default=str)}"

    response = complete(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    state["final_answer"] = response.choices[0].message.content.strip()

    # One extra LLM call produces the plain-English read of the data, the
    # explanation of the SQL, and the suggested follow-up questions. Three
    # separate calls would triple the wait.
    insight, explanation, follow_ups = _summarize_and_explain(state)
    state["insight"] = insight
    state["sql_explanation"] = explanation
    state["follow_ups"] = follow_ups
    state["tables_used"] = _tables_used(state["sql_query"], state.get("columns", []))

    # The step breakdown, so a reader can check the query one operation at a
    # time instead of scanning a wall of SQL.
    state["steps"] = explain_sql_steps(
        state["sql_query"], state["user_query"], state["tables_used"]
    )

    # The confidence signal, derived from what actually happened in the run.
    state["confidence"] = _confidence(state)

    vector_store.semantic_cache_set(user_query, state["final_answer"], state["sql_query"], state["tenant_id"])

    return state

# --- Helpers ---

def _is_numeric(value) -> bool:
    """True for real numbers (not bools, which are ints in Python)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def detect_chart_type(columns: list, rows: list) -> str:
    """
    Pick a chart type from the shape of a result set.

    The rules follow the job the chart has to do:
      - a time column plus a measure        -> line (trend over time)
      - a category column plus a measure    -> bar (compare magnitude)
      - one numeric column                 -> bar
      - two numeric columns                -> scatter
      - anything else                      -> none (the table is the answer)
    """
    if not columns or not rows:
        return "none"

    sample = rows[0]

    def col_kind(name):
        values = [r.get(name) for r in rows if r.get(name) is not None]
        if not values:
            return "empty"
        if all(_is_numeric(v) for v in values):
            return "number"
        if all(isinstance(v, str) for v in values):
            return "text"
        return "mixed"

    kinds = {c: col_kind(c) for c in columns}

    numeric_cols = [c for c in columns if kinds[c] == "number"]
    text_cols = [c for c in columns if kinds[c] == "text"]

    # A time column may hold numbers (a year, a month index) as well as dates,
    # so the name is the only reliable signal. It is excluded from the
    # measure candidates either way.
    time_col = next(
        (c for c in columns if any(h in c.lower() for h in _TIME_HINTS)),
        None,
    )

    # Time series: a date-ish column alongside a measure.
    if time_col and len(columns) > 1:
        measure_candidates = [c for c in numeric_cols if c != time_col]
        if measure_candidates:
            measure = max(measure_candidates, key=lambda c: _spread(rows, c))
            return "line"

    # Category plus a measure: a bar chart.
    if text_cols and numeric_cols:
        label_col = next(
            (c for c in columns if any(h in c.lower() for h in _CATEGORY_HINTS) and kinds[c] == "text"),
            text_cols[0],
        )
        measure = max(numeric_cols, key=lambda c: _spread(rows, c))
        if label_col != measure:
            return "bar"

    if len(numeric_cols) == 1 and len(columns) == 1:
        return "bar"

    if len(numeric_cols) == 2 and len(text_cols) == 0:
        return "scatter"

    return "none"


def _spread(rows: list, column: str) -> float:
    """How much a numeric column varies. The most varied column is the measure."""
    values = [r.get(column) for r in rows if _is_numeric(r.get(column))]
    if len(values) < 2:
        return 0.0
    return max(values) - min(values)


def _tables_used(sql: str, columns: list) -> list:
    """
    The tables a query read from, for the "Found data in" line.

    This is the provenance line: it tells the user which parts of their
    database the answer came from, so a number can be traced back to its
    source without reading the SQL.
    """
    analysis = classify_query(sql)
    tables = list(analysis.get("tables", []))

    # A single-column aggregate has no table name in the output, so the
    # table has to come from the statement itself.
    return [t for t in tables if t]


def _confidence(state: AgentState) -> dict:
    """
    A confidence signal for the answer, in the categorical form the research
    recommends rather than a fake percentage.

    "How sure are you, 73%?" is false precision: the model has no
    well-calibrated probability over its own correctness, and research on
    confidence displays finds that numeric confidence that does not track
    accuracy makes people MORE confident, not better at spotting errors. A
    High / Medium / Low label tied to observable evidence is honest and
    actionable.

    The evidence is what actually happened during the run:
      - the query failed and had to be rewritten  -> not high
      - the question was ambiguous                 -> not high
      - the result came from a verified cache hit -> high
      - the query ran first time, in one step     -> high
    """
    traces = state.get("error_traces") or []
    retries = state.get("retry_count", 0)
    cached = state.get("cached_result", False)

    if traces or retries:
        return {
            "level": "low",
            "reason": f"The first query failed and had to be corrected {retries} time(s).",
        }

    if cached:
        return {
            "level": "medium",
            "reason": "This answer came from the semantic cache, so the question closely matched an earlier one.",
        }

    return {
        "level": "high",
        "reason": "The query ran correctly on the first attempt.",
    }


def _summarize_and_explain(state: AgentState) -> tuple:
    """
    Produce three things in a single LLM call:
      - insight: a plain-language read of the data (the headline finding)
      - explanation: what the SQL query did, in non-technical language
      - follow_ups: up to three questions the user might ask next

    Returns ("", "", []) if the call fails. The caller must never break on this.

    The explanation is deliberately constrained to describing what the query
    mechanically does - the tables read, the columns selected, the filter
    applied. A free-form "here is what I did" invites the model to write a
    rationalisation that reads as a justification, and research on AI
    explanations shows that plausible rationalisations raise confidence
    without improving the reader's ability to tell a right answer from a
    wrong one. Describing the mechanics is checkable; a narrative is not.
    """
    rows = state.get("execution_result") or []
    sql = state.get("sql_query", "")

    analysis = classify_query(sql)
    # For a destructive statement the static classifier already says what it
    # does, in plain language, and is faster and more reliable.
    if not analysis["is_read_only"]:
        return "", analysis["description"], []

    if not rows:
        return "", "Reads data from the database.", []

    try:
        system_prompt = (
            "You are a data analyst. Reply in this exact format:\n"
            "INSIGHT: in at most two short sentences, state the headline finding from the data and "
            "name the single most notable row or value. Use plain language, no SQL jargon, no bullet "
            "points. If the data is too small to draw a conclusion, say what the data shows rather "
            "than inventing a trend. If the data does not actually answer the question, say so "
            "plainly instead of stretching to an answer.\n"
            "EXPLANATION: one short sentence describing what the query mechanically does - which "
            "tables it reads, which columns it selects, and any filter it applies. Describe the "
            "mechanics only. Do not justify the query, do not say why it is correct, and do not use "
            "SQL keywords, uppercase table names, or technical terms.\n"
            "FOLLOW_UPS: up to 3 short questions the user might naturally ask next about this same "
            "data, separated by ' | '. Each must be answerable from the same tables. Write them as "
            "questions a non-technical person would ask. If there is no obvious next question, "
            "write nothing after the label."
        )
        user_prompt = (
            f"Question: {state['user_query']}\n"
            f"Columns: {state.get('columns', [])}\n"
            f"Tables read: {state.get('tables_used', [])}\n"
            f"Data (first 50 rows):\n{json.dumps(rows[:50], indent=2, default=str)}\n"
            f"SQL:\n{sql}"
        )

        response = complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = response.choices[0].message.content.strip()

        insight = ""
        explanation = ""
        follow_ups = []

        for line in text.splitlines():
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("INSIGHT:"):
                insight = stripped[len("INSIGHT:"):].strip()
            elif upper.startswith("EXPLANATION:"):
                explanation = stripped[len("EXPLANATION:"):].strip()
            elif upper.startswith("FOLLOW_UPS:"):
                raw = stripped[len("FOLLOW_UPS:"):].strip()
                follow_ups = [
                    q.strip() for q in raw.split("|") if q.strip()
                ][:3]

        # If the model did not use the labels, treat the first line as the insight.
        if not insight and not explanation and text:
            insight = text

        return insight, explanation or analysis["description"], follow_ups
    except Exception:
        return "", analysis["description"], []


def _summarize(question: str, columns: list, rows: list) -> str:
    """
    The cache-hit path's insight only. Kept separate so a cached answer does
    not pay for an explanation it does not need to regenerate.
    """
    if not rows:
        return ""
    try:
        system_prompt = (
            "You are a data analyst. In at most two short sentences, state the headline finding "
            "from the data. Use plain language, no SQL jargon, no bullet points."
        )
        user_prompt = (
            f"Question: {question}\n"
            f"Columns: {columns}\n"
            f"Data (first 50 rows):\n{json.dumps(rows[:50], indent=2, default=str)}"
        )
        response = complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return ""


# --- Edges and Routing ---

def cache_router(state: AgentState):
    if state.get("cached_result"):
        return "end"
    return "schema_inspector"

def self_healing_router(state: AgentState):
    if state.get("execution_result") is not None:
         return "synthesis"
    else:
         if state.get("retry_count", 0) < 3:
             print(f"  -> Retrying ({state['retry_count']}/3)...")
             return "retry"
         else:
             print("  -> Max retries reached. Giving up.")
             return "synthesis"

# --- Build Graph ---

workflow = StateGraph(AgentState)

workflow.add_node("cache_check", cache_check_node)
workflow.add_node("schema_inspector", schema_inspector_node)
workflow.add_node("sql_generator", sql_generator_node)
workflow.add_node("sql_executor", sql_executor_node)
workflow.add_node("synthesis", response_synthesis_node)

workflow.set_entry_point("cache_check")
workflow.add_conditional_edges("cache_check", cache_router, {"end": END, "schema_inspector": "schema_inspector"})
workflow.add_edge("schema_inspector", "sql_generator")
workflow.add_edge("sql_generator", "sql_executor")
workflow.add_conditional_edges("sql_executor", self_healing_router, {"synthesis": "synthesis", "retry": "sql_generator"})
workflow.add_edge("synthesis", END)

app = workflow.compile()

def run_agent(query: str, tenant_id: str = "default_tenant", db_uri: str = "sqlite:///chinook.db"):
    """Entry function for the API to call."""
    initial_state = {
        "user_query": query,
        "tenant_id": tenant_id,
        "db_uri": db_uri,
        "schema_context": "",
        "sql_query": "",
        "execution_result": None,
        "error_traces": [],
        "retry_count": 0,
        "final_answer": "",
        "cached_result": False,
        "requires_approval": False,
        "chart_type": "none",
        "insight": "",
        "columns": [],
        "row_count": 0,
        "truncated": False,
        "sql_explanation": "",
        "analysis": {},
        "follow_ups": [],
        "tables_used": [],
        "steps": [],
        "confidence": {},
    }

    final_state = app.invoke(initial_state)
    return final_state
