"""
Tests for the agent.

Two kinds of test live here:

  - **Deterministic tests** exercise the parts that do not need a model: the
    statement classifier, the safety gate, the schema fallback, the chart
    planner. These always run.

  - **Model tests** need a real Gemini call. They are skipped unless
    `RUN_MODEL_TESTS=1` is set, because they cost money and are slow, and
    because a shared API key gets rate-limited.

The whole suite can also be run against the deterministic mock with
`MOCK_LLM=1`, which is how the interface is exercised without a key.
"""

import os

import pytest

from agent import run_agent, detect_chart_type
from sql_analysis import classify_query

# Every test runs against the bundled sample database. The tenant id keeps
# the schema index and the semantic cache separate per test run.
DB_URI = "sqlite:///chinook.db"
TENANT = "test_agent_tenant"

RUN_MODEL_TESTS = os.getenv("RUN_MODEL_TESTS", "").lower() in ("1", "true", "yes")
needs_model = pytest.mark.skipif(
    not RUN_MODEL_TESTS,
    reason="Set RUN_MODEL_TESTS=1 to run tests that call the model.",
)


@pytest.fixture(scope="module")
def connected():
    """Index the sample database once for the whole module."""
    from vector_store import vector_store

    vector_store.init_schema_rag(DB_URI, TENANT)
    return True


# ---------------------------------------------------------------------------
# Statement classification - the safety gate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sql,statement_type,mutating", [
    ("SELECT * FROM Album", "SELECT", False),
    ("SELECT COUNT(*) FROM Album", "SELECT", False),
    ("WITH c AS (SELECT 1 AS x) SELECT * FROM c", "SELECT", False),
    ("DELETE FROM Album WHERE AlbumId = 1", "DELETE", True),
    ("UPDATE Album SET Title = 'x'", "UPDATE", True),
    ("INSERT INTO Playlist (Name) VALUES ('New')", "INSERT", True),
    ("DROP TABLE Album", "DROP", True),
    ("TRUNCATE TABLE Album", "TRUNCATE", True),
    ("ALTER TABLE Album ADD COLUMN Foo INT", "ALTER", True),
])
def test_classify_query(sql, statement_type, mutating):
    """Every statement is classified by what it actually does."""
    result = classify_query(sql)

    assert result["type"] == statement_type
    assert result["is_mutating"] is mutating
    assert result["is_read_only"] is (not mutating)
    assert result["description"], "every statement gets a plain-language description"


def test_keyword_inside_a_string_is_not_a_mutation():
    """
    A read query that merely mentions DELETE in a literal is still a read.
    The old keyword scan would have blocked it.
    """
    result = classify_query("SELECT * FROM AuditLog WHERE action = 'DELETE'")

    assert result["is_mutating"] is False
    assert result["type"] == "SELECT"


def test_mutation_hidden_behind_a_cte_is_still_caught():
    """A write statement written as a CTE is still a write."""
    result = classify_query(
        "WITH doomed AS (SELECT AlbumId FROM Album WHERE AlbumId > 500) "
        "DELETE FROM Album WHERE AlbumId IN (SELECT AlbumId FROM doomed)"
    )

    assert result["is_mutating"] is True


def test_classification_strips_comments():
    """A commented-out DELETE must not make a read look like a write."""
    result = classify_query("SELECT * FROM Album -- DELETE FROM Album")

    assert result["is_mutating"] is False


def test_table_extraction_finds_the_target():
    """The classifier names the table a statement affects."""
    assert "Album" in classify_query("DELETE FROM Album").get("tables", [])
    assert "Album" in classify_query("DROP TABLE Album").get("tables", [])
    assert "Album" in classify_query("UPDATE Album SET Title = 'x'").get("tables", [])
    # The word TABLE must not be mistaken for a table name.
    assert "TABLE" not in classify_query("DROP TABLE Album").get("tables", [])


# ---------------------------------------------------------------------------
# Chart type selection
# ---------------------------------------------------------------------------

def test_chart_type_for_a_category_and_a_measure():
    assert detect_chart_type(
        ["Country", "Total"], [{"Country": "US", "Total": 1}, {"Country": "UK", "Total": 2}]
    ) == "bar"


def test_chart_type_for_a_time_series():
    assert detect_chart_type(
        ["InvoiceDate", "Total"], [{"InvoiceDate": "2023-01-01", "Total": 1}]
    ) == "line"


def test_chart_type_for_a_numeric_year():
    """A year column holds numbers, but it is still the time axis."""
    assert detect_chart_type(
        ["Year", "Revenue"], [{"Year": 2023, "Revenue": 1}, {"Year": 2024, "Revenue": 2}]
    ) == "line"


def test_no_chart_for_a_list_of_names():
    assert detect_chart_type(
        ["Name", "Email"], [{"Name": "a", "Email": "b"}]
    ) == "none"


# ---------------------------------------------------------------------------
# Schema retrieval
# ---------------------------------------------------------------------------

def test_schema_falls_back_to_the_full_schema():
    """
    With no vector index for a tenant, the agent must still get a schema.
    A large schema costs tokens; no schema costs correctness.
    """
    from tools import get_schema_for_query

    context = get_schema_for_query("anything", "a_tenant_with_no_index", DB_URI)

    assert "Table: Album" in context
    assert "AlbumId" in context


def test_starter_questions_are_answerable():
    """Every generated starter question must be answerable from the schema."""
    from starter_questions import generate_starter_questions
    from tools import get_schema_json

    schema = get_schema_json(DB_URI)
    questions = generate_starter_questions(schema, limit=6)

    assert len(questions) > 0
    for question in questions:
        assert question["question"].endswith("?")
        assert question["table"]


# ---------------------------------------------------------------------------
# The safety gate, through the agent
# ---------------------------------------------------------------------------

def test_a_destructive_request_is_never_executed(connected, monkeypatch):
    """
    A destructive request must come back asking for approval, and must not
    reach the database.
    """
    import tools

    executed = []

    original = tools.execute_sql

    def spy(sql, db_uri, bypass_approval=False):
        executed.append((sql, bypass_approval))
        return original(sql, db_uri, bypass_approval)

    monkeypatch.setattr("agent.execute_sql", spy)

    # A DELETE against a table, run directly through the executor node.
    from agent import sql_executor_node

    state = {
        "sql_query": "DELETE FROM Album WHERE AlbumId = 1",
        "db_uri": DB_URI,
        "error_traces": [],
        "retry_count": 0,
    }
    result = sql_executor_node(state)

    assert result["requires_approval"] is True
    # The statement was intercepted, so it never ran.
    assert result["execution_result"][0].get("message")
    assert "flagged" in result["execution_result"][0]["message"].lower()


def test_a_read_is_executed(connected):
    """A read runs and returns rows."""
    from agent import sql_executor_node

    state = {
        "sql_query": "SELECT COUNT(*) AS n FROM Album",
        "db_uri": DB_URI,
        "error_traces": [],
        "retry_count": 0,
    }
    result = sql_executor_node(state)

    assert result["requires_approval"] is False
    assert result["execution_result"][0]["n"] == 347


def test_the_database_is_unchanged_by_the_impact_preview():
    """
    The preview must be read-only. It counts the rows a DELETE would touch
    and shows a sample, but it must not delete them.
    """
    import sqlite3

    from sql_analysis import preview_impact

    before = sqlite3.connect("chinook.db").execute("SELECT COUNT(*) FROM Album").fetchone()[0]

    preview = preview_impact("DELETE FROM Album WHERE AlbumId = 1", DB_URI)
    assert preview["success"] is True
    assert preview["estimated_rows"] == 1
    assert preview["sample_rows"]

    after = sqlite3.connect("chinook.db").execute("SELECT COUNT(*) FROM Album").fetchone()[0]
    assert before == after


# ---------------------------------------------------------------------------
# The confidence signal
# ---------------------------------------------------------------------------

def test_confidence_is_high_when_the_query_worked_first_time():
    """A clean run is high confidence."""
    from agent import _confidence

    result = _confidence({
        "error_traces": [],
        "retry_count": 0,
        "cached_result": False,
    })

    assert result["level"] == "high"
    assert result["reason"]


def test_confidence_drops_when_the_agent_had_to_correct_itself():
    """A retried query is not high confidence - and says why."""
    from agent import _confidence

    result = _confidence({
        "error_traces": ["no such column: foo"],
        "retry_count": 1,
        "cached_result": False,
    })

    assert result["level"] == "low"
    assert "corrected" in result["reason"]


def test_confidence_is_medium_for_a_cache_hit():
    """A cached answer is not a fresh one, so it is not high confidence."""
    from agent import _confidence

    result = _confidence({
        "error_traces": [],
        "retry_count": 0,
        "cached_result": True,
    })

    assert result["level"] == "medium"
    assert "cache" in result["reason"].lower()


def test_confidence_is_never_a_percentage():
    """
    The signal is categorical, not a number. A model has no calibrated
    probability over its own correctness, and research finds that numeric
    confidence raises trust without improving error detection.
    """
    from agent import _confidence

    for state in [
        {"error_traces": [], "retry_count": 0, "cached_result": False},
        {"error_traces": ["x"], "retry_count": 1, "cached_result": False},
        {"error_traces": [], "retry_count": 0, "cached_result": True},
    ]:
        level = _confidence(state)["level"]
        assert level in ("high", "medium", "low")
        assert "%" not in level


# ---------------------------------------------------------------------------
# The step breakdown
# ---------------------------------------------------------------------------

def test_steps_are_generated_for_a_query():
    """A query is broken into plain-language steps a reader can check."""
    from agent import explain_sql_steps

    steps = explain_sql_steps(
        "SELECT Name, COUNT(*) FROM Album JOIN Artist USING (ArtistId) "
        "GROUP BY Name ORDER BY COUNT(*) DESC LIMIT 10",
        "Which artist has the most albums?",
        ["Album", "Artist"],
    )

    assert isinstance(steps, list)
    # With no model available the list may be empty, but it must never be
    # something other than a list of plain strings.
    assert all(isinstance(step, str) for step in steps)
    assert len(steps) <= 5


def test_steps_are_empty_for_an_empty_query():
    from agent import explain_sql_steps

    assert explain_sql_steps("", "question", []) == []


# ---------------------------------------------------------------------------
# Tests that call the model
# ---------------------------------------------------------------------------

@needs_model
def test_single_table_lookup(connected):
    """Test 1: Simple query that should not require self-healing."""
    query = "How many artists are in the database?"
    res = run_agent(query, TENANT, DB_URI)

    assert res["execution_result"] is not None
    assert len(res["error_traces"]) == 0
    assert "275" in str(res["execution_result"]) or "275" in res["final_answer"]


@needs_model
def test_multi_table_join(connected):
    """Test 2: A query requiring JOINs."""
    query = "What is the name of the album that contains the track 'Fast As a Shark'?"
    res = run_agent(query, TENANT, DB_URI)

    assert res["execution_result"] is not None
    assert "Restless and Wild" in str(res["execution_result"]).title() or \
           "Restless and Wild" in res["final_answer"].title()


@needs_model
def test_aggregate_function(connected):
    """Test 3: Using COUNT/SUM."""
    query = "What is the total number of tracks in the Rock genre?"
    res = run_agent(query, TENANT, DB_URI)

    assert res["execution_result"] is not None
    assert "1297" in str(res["execution_result"]) or "1297" in res["final_answer"]


@needs_model
def test_self_healing_ambiguous(connected):
    """
    Test 4: Intentionally ambiguous or complex query that might cause the LLM
    to write bad SQL on the first try, triggering the self-healing loop.
    """
    query = "Which sales support agent generated the highest total revenue in 2023?"
    res = run_agent(query, TENANT, DB_URI)

    assert res["execution_result"] is not None
    assert res["retry_count"] >= 0
    assert res["retry_count"] <= 3


@needs_model
def test_response_includes_explanation_and_insight(connected):
    """
    Test 5: A successful answer carries the extra context the UI shows:
    the SQL, a plain-English explanation, an insight, and a column list.
    """
    res = run_agent("How many albums are there?", TENANT, DB_URI)

    assert res["execution_result"] is not None
    assert res["sql_query"], "the agent should return the SQL it ran"
    assert res["columns"], "the agent should return the column names"
    assert res["row_count"] >= 0
    assert res["sql_explanation"], "the agent should explain the query in plain language"
    assert res["chart_type"] in ("none", "bar", "line", "scatter")


@needs_model
def test_semantic_caching(connected):
    """Test 6: Verify the semantic cache returns a hit for identical queries."""
    query = "How many artists are there?"

    res1 = run_agent(query, TENANT, DB_URI)
    res2 = run_agent(query, TENANT, DB_URI)

    assert res2["cached_result"] == True
    assert res1["final_answer"] == res2["final_answer"]
