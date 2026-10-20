"""
Autonomous NL-to-SQL Agent workflow implemented with LangGraph.

Architecture:
  cache_check -> [Hit: END | Miss: schema_inspector]
  schema_inspector -> sql_generator -> sql_executor
  sql_executor -> [Success: synthesis | Error: sql_generator (retry <= 3)]
  synthesis -> END
"""

import os
import json
import time
from typing import TypedDict, List, Optional
from dotenv import load_dotenv

load_dotenv()

from langgraph.graph import StateGraph, END
from litellm import completion
from tools import get_schema_for_query, execute_sql
from vector_store import vector_store
from sql_analysis import classify_query
import mock_llm

# ==============================================================================
# 1. Configuration
# ==============================================================================

# The model that writes and explains the SQL. Override with the MODEL env var.
MODEL = os.getenv("MODEL", "gemini/gemini-2.5-flash")

# Hints for detecting time-series and category columns for charts
_TIME_HINTS = (
    "date", "time", "year", "month", "day", "week", "quarter", "period",
    "created", "updated", "released", "purchased", "invoiced", "hired", "born",
)

_CATEGORY_HINTS = (
    "name", "title", "category", "genre", "type", "status", "country", "state",
    "city", "region", "department", "artist", "album", "customer", "product",
    "label", "group", "kind", "email", "id",
)


# ==============================================================================
# 2. State Schema
# ==============================================================================

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


# ==============================================================================
# 3. Graph Workflow Nodes
# ==============================================================================

def cache_check_node(state: AgentState):
    """Check if query is already present in semantic cache."""
    print("[Node: cache_check_node]")
    cached = vector_store.semantic_cache_check(state["user_query"], state["tenant_id"])
    if cached:
        print("  -> Cache Hit!")
        state["final_answer"] = cached["answer"]
        state["sql_query"] = cached["sql"]
        state["cached_result"] = True

        # Re-run cached SQL so user receives live data table alongside cached answer
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
            pass
    else:
        print("  -> Cache Miss")
        state["cached_result"] = False
    return state


def schema_inspector_node(state: AgentState):
    """Retrieve relevant schema metadata using Schema-RAG."""
    print("[Node: schema_inspector_node]")
    schema = get_schema_for_query(state["user_query"], state["tenant_id"], state["db_uri"])
    state["schema_context"] = schema
    return state


def sql_generator_node(state: AgentState):
    """Generate or fix SQL query using LLM based on schema and prior error traces."""
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
    return state


def sql_executor_node(state: AgentState):
    """Execute SQL query safely with statement classification and approval gating."""
    print("[Node: sql_executor_node]")
    sql = state["sql_query"]
    db_uri = state["db_uri"]
    print(f"  -> Executing: {sql}")

    res = execute_sql(sql, db_uri)
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
    """Synthesize plain-English response, metadata, insights, steps, and follow-ups."""
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

    # Unified synthesis for insight, query explanation, and follow-up suggestions
    insight, explanation, follow_ups = _summarize_and_explain(state)
    state["insight"] = insight
    state["sql_explanation"] = explanation
    state["follow_ups"] = follow_ups
    state["tables_used"] = _tables_used(state["sql_query"], state.get("columns", []))

    # Step breakdown for human-verifiable logic
    state["steps"] = explain_sql_steps(
        state["sql_query"], state["user_query"], state["tables_used"]
    )

    # Observable confidence calibration
    state["confidence"] = _confidence(state)

    # Store in semantic cache
    vector_store.semantic_cache_set(user_query, state["final_answer"], state["sql_query"], state["tenant_id"])

    return state


# ==============================================================================
# 4. Routing & Conditional Edges
# ==============================================================================

def cache_router(state: AgentState):
    """Route to END on cache hit, or schema_inspector on cache miss."""
    if state.get("cached_result"):
        return "end"
    return "schema_inspector"


def self_healing_router(state: AgentState):
    """Route to synthesis on successful execution, or retry generator on failure (up to 3 times)."""
    if state.get("execution_result") is not None:
        return "synthesis"
    else:
        if state.get("retry_count", 0) < 3:
            print(f"  -> Retrying ({state['retry_count']}/3)...")
            return "retry"
        else:
            print("  -> Max retries reached. Giving up.")
            return "synthesis"


# ==============================================================================
# 5. Graph Construction & Compilation
# ==============================================================================

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


# ==============================================================================
# 6. Public Entrypoint
# ==============================================================================

def run_agent(query: str, tenant_id: str = "default_tenant", db_uri: str = "sqlite:///chinook.db"):
    """Entry function for the API and tests."""
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


# ==============================================================================
# 7. Query Explanation & Analysis Helpers
# ==============================================================================

def explain_sql_steps(sql: str, user_query: str, tables: list) -> list:
    """Break a SQL query into logical plain-language steps."""
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
            if cleaned and cleaned[0].isdigit() and "." in cleaned[:4]:
                cleaned = cleaned.split(".", 1)[1].strip()
            if cleaned:
                steps.append(cleaned)

        return steps[:5]
    except Exception:
        return []


def _tables_used(sql: str, columns: list) -> list:
    """Extract table provenance from SQL query."""
    analysis = classify_query(sql)
    tables = list(analysis.get("tables", []))
    return [t for t in tables if t]


def _confidence(state: AgentState) -> dict:
    """Categorical confidence calibration based on observable runtime evidence."""
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
    """Produce data insight, query explanation, and follow-up suggestions in a single LLM call."""
    rows = state.get("execution_result") or []
    sql = state.get("sql_query", "")

    analysis = classify_query(sql)
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

        if not insight and not explanation and text:
            insight = text

        return insight, explanation or analysis["description"], follow_ups
    except Exception:
        return "", analysis["description"], []


def _summarize(question: str, columns: list, rows: list) -> str:
    """Summarize data headline for semantic cache hit paths."""
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


def _explain_sql(sql: str) -> str:
    """Quick static or classifier explanation of SQL query."""
    analysis = classify_query(sql)
    return analysis.get("description", "Reads data from the database.")


# ==============================================================================
# 8. Visualization & Chart Classification
# ==============================================================================

def _is_numeric(value) -> bool:
    """True for real numbers (excluding booleans)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def detect_chart_type(columns: list, rows: list) -> str:
    """
    Select appropriate chart type from result set shape:
      - time column + measure      -> line
      - category column + measure  -> bar
      - single numeric column      -> bar
      - two numeric columns        -> scatter
      - other                      -> none
    """
    if not columns or not rows:
        return "none"

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

    time_col = next(
        (c for c in columns if any(h in c.lower() for h in _TIME_HINTS)),
        None,
    )

    if time_col and len(columns) > 1:
        measure_candidates = [c for c in numeric_cols if c != time_col]
        if measure_candidates:
            return "line"

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
    """Calculate variance range of numeric column."""
    values = [r.get(column) for r in rows if _is_numeric(r.get(column))]
    if len(values) < 2:
        return 0.0
    return max(values) - min(values)


# ==============================================================================
# 9. LLM Execution & Retry Wrapper
# ==============================================================================

def complete(messages, **kwargs):
    """Call model with transient failure backoff or deterministic test mock."""
    if mock_llm.MOCK_ENABLED:
        return mock_llm.mock_completion(messages)

    last_error = None

    for attempt in range(4):
        try:
            return completion(model=MODEL, messages=messages, **kwargs)
        except Exception as exc:  # noqa: BLE001
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
