import re
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError

from sql_analysis import classify_query, preview_impact

# Rows beyond this are not sent to the browser. A result set of a million rows
# would stall the UI, and no one reads a million rows in a chat bubble.
MAX_ROWS_RETURNED = 5000


def get_schema_json(db_uri: str) -> dict:
    """
    Returns a structured dictionary of all tables and their columns.
    Format: {"tables": [{"name": "table1", "columns": [{"name": "c1", "type": "int"}]}]}
    """
    try:
        engine = create_engine(db_uri)
        inspector = inspect(engine)

        tables = []
        for table_name in inspector.get_table_names():
            columns = []
            for col in inspector.get_columns(table_name):
                columns.append({
                    "name": col["name"],
                    "type": str(col["type"])
                })
            tables.append({
                "name": table_name,
                "columns": columns
            })

        return {"success": True, "tables": tables}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _jsonable(value):
    """Convert a database value into something JSON-serialisable."""
    import datetime
    import decimal
    import uuid

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return str(value)


def execute_sql(sql: str, db_uri: str, bypass_approval: bool = False) -> dict:
    """
    Executes a SQL query against the database specified by db_uri.
    Intercepts destructive queries for Human-in-the-Loop approval unless bypassed.

    The destructive check uses a real statement classifier rather than a keyword
    scan, so a read query that merely mentions DELETE in a string literal
    (e.g. WHERE note = 'please delete') is not falsely blocked.
    """
    analysis = classify_query(sql)

    # 1. HITL Interception
    if analysis["is_mutating"] and not bypass_approval:
        return {
            "success": True,
            "requires_approval": True,
            "result": None,
            "message": "Query flagged for Human-in-the-Loop approval.",
            "analysis": analysis,
        }

    # 2. Execute the query
    try:
        engine = create_engine(db_uri)
        with engine.connect() as connection:
            # We use an explicit transaction block for destructive queries
            trans = connection.begin()
            try:
                result = connection.execute(text(sql))

                # If it's a SELECT returning rows
                if result.returns_rows:
                    result_data = []
                    columns = []
                    truncated = False
                    for index, row in enumerate(result):
                        if index >= MAX_ROWS_RETURNED:
                            truncated = True
                            break
                        row_dict = {}
                        for k, v in row._mapping.items():
                            row_dict[k] = _jsonable(v)
                        if index == 0:
                            columns = list(row._mapping.keys())
                        result_data.append(row_dict)
                    trans.commit()
                    return {
                        "success": True,
                        "requires_approval": False,
                        "result": result_data,
                        "columns": columns,
                        "row_count": len(result_data),
                        "truncated": truncated,
                        "analysis": analysis,
                    }
                else:
                    # For INSERT/UPDATE/DELETE
                    affected = result.rowcount
                    trans.commit()
                    return {
                        "success": True,
                        "requires_approval": False,
                        "result": [{"status": "Success", "rows_affected": affected}],
                        "columns": ["status", "rows_affected"],
                        "row_count": affected,
                        "truncated": False,
                        "analysis": analysis,
                    }
            except Exception as e:
                trans.rollback()
                raise e

    except SQLAlchemyError as e:
        return {
            "success": False,
            "error": f"Database Error: {str(e)}",
            "analysis": analysis,
        }
    except Exception as e:
         return {
            "success": False,
            "error": f"Unexpected Error: {str(e)}",
            "analysis": analysis,
        }


def get_schema_for_query(query: str, tenant_id: str, db_uri: str = ""):
    """
    Uses the Vector Store to find the most relevant schema tables for a specific tenant.

    If the vector store is unavailable or returns nothing, fall back to the full
    schema read straight from the database. Giving the model every table costs
    tokens; giving it no schema costs correctness.
    """
    from vector_store import vector_store

    # Get top 5 tables for this specific tenant
    relevant_schema_docs = vector_store.search_schema(query, tenant_id, k=5)

    if relevant_schema_docs:
        return "\n\n".join(relevant_schema_docs)

    if db_uri:
        schema = get_schema_json(db_uri)
        if schema.get("success") and schema.get("tables"):
            parts = []
            for table in schema["tables"]:
                columns = ", ".join(
                    f"{col['name']} ({col['type']})" for col in table.get("columns", [])
                )
                parts.append(f"Table: {table['name']}\nColumns: {columns}")
            return "\n\n".join(parts)

    return "No schema available. Ensure the database connection is set up and initialized."


def get_row_preview(sql: str, db_uri: str, limit: int = 100) -> dict:
    """
    Run a read-only query and return at most `limit` rows. Used by the
    "run this SQL yourself" panel in the UI.
    """
    analysis = classify_query(sql)
    if analysis["is_mutating"]:
        return {
            "success": False,
            "error": "This statement changes data. Approve it from the chat panel to run it.",
        }

    try:
        engine = create_engine(db_uri)
        with engine.connect() as connection:
            result = connection.execute(text(sql))
            if not result.returns_rows:
                return {"success": True, "result": [], "columns": [], "row_count": 0}

            rows = []
            columns = []
            for index, row in enumerate(result):
                if index >= limit:
                    break
                if index == 0:
                    columns = list(row._mapping.keys())
                rows.append({k: _jsonable(v) for k, v in row._mapping.items()})

            return {
                "success": True,
                "result": rows,
                "columns": columns,
                "row_count": len(rows),
            }
    except SQLAlchemyError as e:
        return {"success": False, "error": f"Database Error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected Error: {str(e)}"}
