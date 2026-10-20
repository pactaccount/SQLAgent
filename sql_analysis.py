"""
Static analysis of SQL statements plus safe impact previews.

This module never executes a destructive statement. It only reads the database
to answer two questions the UI needs before a human approves a change:

  1. "What does this statement do?"  -> classify_query()
  2. "How much will it affect?"      -> preview_impact()

Everything here is read-only. preview_impact() opens a transaction, reads the
rows that match the statement's WHERE clause, and rolls back.
"""

import re
from typing import Optional, Tuple

# Statement types, ordered by the severity of what they do to the database.
MUTATING_TYPES = ("DELETE", "UPDATE", "INSERT", "DROP", "ALTER", "CREATE", "TRUNCATE")

# Verbs that only read data.
READ_TYPES = ("SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN", "PRAGMA")

# Human-readable names for the UI. Keep them plain-language.
_TYPE_LABELS = {
    "SELECT": "Reads data",
    "WITH": "Reads data",
    "SHOW": "Reads data",
    "DESCRIBE": "Reads data",
    "EXPLAIN": "Reads data",
    "PRAGMA": "Reads data",
    "INSERT": "Adds rows",
    "UPDATE": "Changes existing rows",
    "DELETE": "Removes rows",
    "DROP": "Deletes a table or column",
    "ALTER": "Changes a table's structure",
    "CREATE": "Creates a table or index",
    "TRUNCATE": "Removes all rows from a table",
}

# Words that make a statement read-only even though it contains a mutating verb.
# e.g. "SELECT count(*) FROM logs WHERE action = 'DELETE'" is still a read.
_READ_ONLY_CONTEXT = re.compile(
    r"^\s*(select|with|show|describe|explain|pragma)\b", re.IGNORECASE
)


def _strip_comments_and_strings(sql: str) -> str:
    """
    Remove comments and quoted literals so keyword scanning cannot be fooled by
    a string that merely contains the word DELETE.
    """
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    # Replace single-quoted literals with empty string literals.
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    # Replace double-quoted / bracketed identifiers with empty identifiers.
    sql = re.sub(r'"(?:[^"]|"")*"', '""', sql)
    sql = re.sub(r"\[[^\]]*\]", "[]", sql)
    return sql


def classify_query(sql: str) -> dict:
    """
    Classify a SQL statement without touching the database.

    Returns a dict with the statement type, whether it mutates data, the
    tables it touches, and a short plain-language description.
    """
    cleaned = _strip_comments_and_strings(sql or "").strip()
    if not cleaned:
        return {
            "type": "UNKNOWN",
            "label": "Unrecognised statement",
            "is_mutating": False,
            "is_read_only": True,
            "tables": [],
            "description": "No SQL was provided.",
            "risk": "none",
        }

    upper = cleaned.upper()

    # A CTE ("WITH x AS (...) SELECT ...") is a read unless its final verb mutates.
    statement_type = "SELECT"
    if _READ_ONLY_CONTEXT.match(cleaned):
        # Look past the CTE to the verb that actually runs.
        tail = re.search(
            r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE)\b(?![^()]*\))", upper[4:]
        )
        statement_type = tail.group(1) if tail else "SELECT"
    else:
        first_word = re.match(r"[A-Z]+", upper)
        statement_type = first_word.group(0) if first_word else "UNKNOWN"

    # Guard: a read-only context can only be a read.
    if _READ_ONLY_CONTEXT.match(cleaned) and statement_type == "SELECT":
        is_mutating = False
    else:
        is_mutating = statement_type in MUTATING_TYPES

    tables = _extract_tables(cleaned)

    if is_mutating:
        label = _TYPE_LABELS.get(statement_type, "Changes data")
        risk = "high" if statement_type in ("DROP", "TRUNCATE", "DELETE") else "medium"
    else:
        label = _TYPE_LABELS.get(statement_type, "Reads data")
        risk = "none"

    description = _describe(statement_type, tables, is_mutating)

    return {
        "type": statement_type,
        "label": label,
        "is_mutating": is_mutating,
        "is_read_only": not is_mutating,
        "tables": tables,
        "description": description,
        "risk": risk,
    }


def _extract_tables(cleaned_sql: str) -> list:
    """
    Best-effort table name extraction. Handles the common FROM/JOIN/UPDATE/INTO
    forms. Not a full parser, but reliable for the shapes an LLM produces.
    """
    tables = []

    # Ordered so the more specific forms win. The generic "drop X" pattern
    # would otherwise pick up the word TABLE from "DROP TABLE Album".
    patterns = [
        r"\bfrom\s+([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)",
        r"\bjoin\s+([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)",
        r"\bupdate\s+([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)",
        r"\binsert\s+into\s+([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)",
        r"\bdelete\s+from\s+([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)",
        r"\balter\s+table\s+([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)",
        r"\bdrop\s+table\s+(?:if\s+exists\s+)?([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)",
        r"\btruncate\s+(?:table\s+)?([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)",
        r"\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, cleaned_sql, re.IGNORECASE):
            name = re.split(r"\s+", match.group(1))[0]
            # These are keywords, not table names.
            if not name or name.lower() in ("if", "exists", "set", "values", "table", "not"):
                continue
            if name not in tables:
                tables.append(name)

    return tables


def _describe(statement_type: str, tables: list, is_mutating: bool) -> str:
    """A one-sentence, jargon-free description of what the statement does."""
    target = tables[0] if tables else "the database"
    extra = f" and {len(tables) - 1} other table(s)" if len(tables) > 1 else ""

    if statement_type == "SELECT":
        return f"Reads rows from {target}{extra}. Nothing is changed."
    if statement_type == "WITH":
        return f"Reads rows from {target}{extra} using a temporary result. Nothing is changed."
    if statement_type == "DELETE":
        return f"Permanently removes rows from {target}. This cannot be undone."
    if statement_type == "UPDATE":
        return f"Changes the values of existing rows in {target}."
    if statement_type == "INSERT":
        return f"Adds new rows to {target}."
    if statement_type == "DROP":
        return f"Permanently deletes {target} and all of its data. This cannot be undone."
    if statement_type == "TRUNCATE":
        return f"Removes every row from {target}. This cannot be undone."
    if statement_type == "ALTER":
        return f"Changes the structure of {target}."
    if statement_type == "CREATE":
        return f"Creates a new table or index called {target}."
    if is_mutating:
        return f"Modifies {target}."
    return "Reads data. Nothing is changed."


def _where_clause(cleaned_sql: str) -> Optional[str]:
    """Return the WHERE clause of a statement, if it has one."""
    match = re.search(r"\bwhere\b(.*?)(?:\border\s+by\b|\blimit\b|\bgroup\s+by\b|\bhaving\b|$)",
                      cleaned_sql, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    clause = match.group(1).strip()
    return clause or None


def preview_impact(sql: str, db_uri: str, sample_limit: int = 5) -> dict:
    """
    Estimate how many rows a mutating statement would touch, and show a few
    of them, WITHOUT running the statement.

    The preview runs inside a transaction that is always rolled back, so the
    database is left exactly as it was found.
    """
    info = classify_query(sql)
    result = {
        "success": False,
        "type": info["type"],
        "label": info["label"],
        "description": info["description"],
        "risk": info["risk"],
        "tables": info["tables"],
        "estimated_rows": None,
        "sample_rows": [],
        "sample_columns": [],
        "message": "",
    }

    if not info["is_mutating"]:
        result["success"] = True
        result["message"] = "This statement only reads data, so there is nothing to preview."
        return result

    statement_type = info["type"]
    cleaned = _strip_comments_and_strings(sql or "").strip()
    table = info["tables"][0] if info["tables"] else None
    where = _where_clause(cleaned)

    # A WHERE clause is a filter, not a column list - it must not be
    # interpolated into the SELECT list of a preview query.
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import SQLAlchemyError

        engine = create_engine(db_uri)

        if statement_type in ("DELETE", "UPDATE"):
            if not table:
                result["message"] = "Could not work out which table this statement affects."
                return result

            # Count only. Reading is safe; the count is what the user needs.
            count_sql = f"SELECT COUNT(*) AS affected_rows FROM {table}"
            if where:
                count_sql += f" WHERE {where}"

            with engine.connect() as connection:
                trans = connection.begin()
                try:
                    count_row = connection.execute(text(count_sql)).fetchone()
                    result["estimated_rows"] = int(count_row[0]) if count_row else 0

                    # Show a few of the rows that would change.
                    sample_sql = f"SELECT * FROM {table}"
                    if where:
                        sample_sql += f" WHERE {where}"
                    sample_sql += f" LIMIT {int(sample_limit)}"

                    rows = connection.execute(text(sample_sql)).fetchall()
                    if rows:
                        result["sample_columns"] = list(rows[0]._mapping.keys())
                        result["sample_rows"] = [
                            {k: _jsonable(v) for k, v in row._mapping.items()} for row in rows
                        ]
                    trans.rollback()
                except Exception:
                    trans.rollback()
                    raise

            result["success"] = True
            verb = "removed" if statement_type == "DELETE" else "changed"
            result["message"] = (
                f"{result['estimated_rows']} row(s) in {table} would be {verb}. "
                "Nothing has been changed yet."
            )
            return result

        if statement_type == "INSERT":
            with engine.connect() as connection:
                trans = connection.begin()
                try:
                    if table:
                        count_sql = f"SELECT COUNT(*) AS existing_rows FROM {table}"
                        count_row = connection.execute(text(count_sql)).fetchone()
                        result["estimated_rows"] = count_row[0] if count_row else None
                    trans.rollback()
                except Exception:
                    trans.rollback()
                    raise
            result["success"] = True
            result["message"] = (
                "New rows would be added. Nothing has been changed yet."
            )
            return result

        if statement_type in ("DROP", "TRUNCATE"):
            with engine.connect() as connection:
                trans = connection.begin()
                try:
                    if table and statement_type == "TRUNCATE":
                        count_sql = f"SELECT COUNT(*) AS affected_rows FROM {table}"
                        count_row = connection.execute(text(count_sql)).fetchone()
                        result["estimated_rows"] = int(count_row[0]) if count_row else 0
                    trans.rollback()
                except Exception:
                    trans.rollback()
                    raise
            result["success"] = True
            result["message"] = (
                f"{table or 'The table'} and everything in it would be permanently removed. "
                "Nothing has been changed yet."
            )
            return result

        result["success"] = True
        result["message"] = "Review the statement before approving it."
        return result

    except SQLAlchemyError as exc:
        result["message"] = f"Could not preview this statement: {exc}"
        return result
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI as a message
        result["message"] = f"Could not preview this statement: {exc}"
        return result


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
