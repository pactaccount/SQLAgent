import os
import json
from typing import TypedDict, List, Optional
from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
from litellm import completion
from tools import get_schema_for_query, execute_sql
from vector_store import vector_store

MODEL = "gemini/gemini-3.6-flash"

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
    else:
        print("  -> Cache Miss")
        state["cached_result"] = False
    return state

def schema_inspector_node(state: AgentState):
    """Retrieve relevant schema for the user query."""
    print("[Node: schema_inspector_node]")
    schema = get_schema_for_query(state["user_query"], state["tenant_id"])
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

    response = completion(
        model=MODEL,
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

def sql_executor_node(state: AgentState):
    """Execute the SQL safely."""
    print("[Node: sql_executor_node]")
    sql = state["sql_query"]
    db_uri = state["db_uri"]
    print(f"  -> Executing: {sql}")
    
    res = execute_sql(sql, db_uri)
    
    if res["success"]:
        if res.get("requires_approval"):
            state["requires_approval"] = True
            state["execution_result"] = [{"message": res["message"]}]
            state["final_answer"] = "This query modifies data and requires your approval. Please review the SQL below."
        else:
            state["requires_approval"] = False
            state["execution_result"] = res["result"]
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
    
    system_prompt = "You are a helpful data analyst. Synthesize the raw database results into a natural, polite response to the user's question."
    user_prompt = f"Question: {user_query}\n\nData Result:\n{json.dumps(result_data, indent=2)}"
    
    response = completion(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )
    
    state["final_answer"] = response.choices[0].message.content.strip()
    
    vector_store.semantic_cache_set(user_query, state["final_answer"], state["sql_query"], state["tenant_id"])
    
    return state

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

def run_agent(query: str, tenant_id: str, db_uri: str):
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
        "requires_approval": False
    }
    
    final_state = app.invoke(initial_state)
    return final_state
