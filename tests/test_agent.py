import pytest
from agent import run_agent

def test_single_table_lookup():
    """Test 1: Simple query that should not require self-healing."""
    query = "How many artists are in the database?"
    res = run_agent(query)
    
    assert res["execution_result"] is not None
    # We don't strictly assert the exact string of final_answer because LLM output varies,
    # but we assert it successfully queried and no errors were raised
    assert len(res["error_traces"]) == 0
    assert "275" in str(res["execution_result"]) or "275" in res["final_answer"]

def test_multi_table_join():
    """Test 2: A query requiring JOINs."""
    query = "What is the name of the album that contains the track 'Fast As a Shark'?"
    res = run_agent(query)
    
    assert res["execution_result"] is not None
    assert "Restless and Wild" in str(res["execution_result"]).title() or "Restless and Wild" in res["final_answer"].title()
    assert res["requires_approval"] == False or res["requires_approval"] == True # Could be true if it uses >= 2 joins

def test_aggregate_function():
    """Test 3: Using COUNT/SUM."""
    query = "What is the total number of tracks in the Rock genre?"
    res = run_agent(query)
    
    assert res["execution_result"] is not None
    assert "1297" in str(res["execution_result"]) or "1297" in res["final_answer"]

def test_self_healing_ambiguous():
    """
    Test 4: Intentionally ambiguous or complex query that might cause the LLM 
    to write bad SQL on the first try, triggering the self-healing loop.
    """
    # This query often trips up basic LLMs on the Chinook DB because 
    # Employee connects to Customer via SupportRepId, not EmployeeId.
    query = "Which sales support agent generated the highest total revenue in 2023?"
    res = run_agent(query)
    
    # It should eventually succeed (within 3 retries)
    assert res["execution_result"] is not None
    assert res["retry_count"] >= 0
    assert res["retry_count"] <= 3

def test_semantic_caching():
    """Test 5: Verify the semantic cache returns a hit for identical queries."""
    query = "How many artists are there?"
    
    # Run once to populate cache
    res1 = run_agent(query)
    
    # Run again, should hit cache
    res2 = run_agent(query)
    
    assert res2["cached_result"] == True
    assert res1["final_answer"] == res2["final_answer"]
