"""Bounded SQL/clarification workflow over the actual registered SQLite database."""

import json
from typing import TypedDict
from langgraph.graph import StateGraph, END
from sqlglot.errors import SqlglotError
from seaql.database import (
    get_schema_for_query,
    execute_sql,
    classify_sql,
    get_schema_json,
)
from seaql.model import complete
from seaql.policy import POLICY, CHECKLIST, GENERIC_POLICY

PROMPT_VERSION = "sqlite-v3"


class AgentState(TypedDict, total=False):
    user_query: str
    tenant_id: str
    db_uri: str
    business_rules: str
    schema_context: str
    sql_query: str
    execution_result: list | None
    error_traces: list
    retry_count: int
    final_answer: str
    cached_result: bool
    requires_approval: bool
    clarification: bool
    truncated: bool
    history: list
    model_id: str
    attempts: list


def prepare(state):
    state["schema_context"] = get_schema_for_query(
        state["user_query"], state["tenant_id"], state["db_uri"]
    )
    tables = {table["name"] for table in get_schema_json(state["db_uri"])["tables"]}
    state["business_rules"] = (
        POLICY
        if {"orders", "customers", "order_items", "products"} <= tables
        else GENERIC_POLICY
    )
    return state


def generate_sql(state):
    system = (
        'Return ONLY valid JSON: {"action":"sql","sql":"..."} or '
        '{"action":"clarify","question":"..."}. Use the schema and business rules. '
        "Do not assume that an ambiguous question is an instruction to change data.\n"
        + state["business_rules"]
        + "\nSchema:\n"
        + state["schema_context"]
    )
    user = "Question: " + state["user_query"] + "\n\n" + CHECKLIST
    if state["error_traces"]:
        user += (
            "\nPrevious SQL: "
            + state["sql_query"]
            + "\nFailure: "
            + state["error_traces"][-1]
            + "\nCorrect the query or ask clarification."
        )
    try:
        text, model = complete(
            [{"role": "system", "content": system}]
            + state["history"]
            + [{"role": "user", "content": user}]
        )
        state["model_id"] = model
        state["attempts"].append({"raw_output": text, "model": model})
        content = text.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("Expected a JSON object.")
        action = parsed.get("action")
        if (
            action == "clarify"
            and isinstance(parsed.get("question"), str)
            and parsed["question"].strip()
        ):
            state.update(
                clarification=True,
                final_answer=parsed["question"].strip(),
                sql_query="",
            )
        elif (
            action == "sql"
            and isinstance(parsed.get("sql"), str)
            and parsed["sql"].strip()
        ):
            state["sql_query"] = parsed["sql"].strip()
            classify_sql(state["sql_query"])
        else:
            raise ValueError("Model returned an invalid SQL/clarification response.")
    except (ValueError, TypeError, KeyError, SqlglotError) as e:
        state["error_traces"].append("Invalid model output: " + str(e))
        state["retry_count"] += 1
        state["sql_query"] = ""
    return state


def after_generation(state):
    if state.get("clarification"):
        return "end"
    if state["sql_query"]:
        return "execute"
    return "generate" if state["retry_count"] < 3 else "summarize"


def execute(state):
    result = execute_sql(state["sql_query"], state["db_uri"])
    state["attempts"][-1].update(
        sql=state["sql_query"],
        execution_success=result["success"],
        execution_error=result.get("error"),
        requires_approval=result.get("requires_approval", False),
    )
    if not result["success"]:
        state["error_traces"].append(result["error"])
        state["retry_count"] += 1
    elif result.get("requires_approval"):
        state.update(
            requires_approval=True,
            final_answer="This statement changes the database. Review it before approval.",
        )
    else:
        state.update(
            execution_result=result["result"], truncated=result.get("truncated", False)
        )
    return state


def after_execution(state):
    if state.get("requires_approval"):
        return "end"
    if state["execution_result"] is not None:
        return "summarize"
    return "generate" if state["retry_count"] < 3 else "summarize"


def summarize(state):
    rows = state["execution_result"]
    if rows is None:
        state["final_answer"] = (
            "No valid query result was produced. See the recorded errors."
        )
        return state
    # Deterministic factual rendering cannot erase successful rows or invent a summary.
    if len(rows) == 1:
        state["final_answer"] = "; ".join(
            f"{k}: {v if v is not None else 'NULL'}" for k, v in rows[0].items()
        )
    else:
        state["final_answer"] = f"Returned {len(rows)} rows. See the results below."
    if state.get("truncated"):
        state["final_answer"] += (
            " Results reached the row limit; refine your question for a complete result."
        )
    return state


workflow = StateGraph(AgentState)
workflow.add_node("prepare", prepare)
workflow.add_node("generate", generate_sql)
workflow.add_node("execute", execute)
workflow.add_node("summarize", summarize)
workflow.set_entry_point("prepare")
workflow.add_edge("prepare", "generate")
workflow.add_conditional_edges(
    "generate",
    after_generation,
    {
        "end": END,
        "execute": "execute",
        "generate": "generate",
        "summarize": "summarize",
    },
)
workflow.add_conditional_edges(
    "execute",
    after_execution,
    {"end": END, "generate": "generate", "summarize": "summarize"},
)
workflow.add_edge("summarize", END)
app = workflow.compile()


def run_agent(query, tenant_id, db_uri, history=None):
    state = dict(
        user_query=query,
        tenant_id=tenant_id,
        db_uri=db_uri,
        history=history or [],
        schema_context="",
        sql_query="",
        execution_result=None,
        error_traces=[],
        retry_count=0,
        final_answer="",
        cached_result=False,
        requires_approval=False,
        clarification=False,
        truncated=False,
        model_id="unknown",
        attempts=[],
    )
    return app.invoke(state, {"recursion_limit": 20})
