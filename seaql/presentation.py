"""Deterministic presentation metadata for the existing browser interface."""

import sqlglot
from sqlglot import exp
from seaql.database import classify_sql, execute_sql


def analysis(sql):
    kind = classify_sql(sql)
    tree = sqlglot.parse_one(sql, read="sqlite")
    tables = sorted({table.name for table in tree.find_all(exp.Table)})
    return {
        "statement_type": tree.key.upper(),
        "is_mutating": kind == "write",
        "requires_approval": kind == "write",
        "tables": tables,
        "description": "Changes database records or structure."
        if kind == "write"
        else "Reads database records.",
    }


def preview(sql, uri):
    details = analysis(sql)
    tree = sqlglot.parse_one(sql, read="sqlite")
    target = tree.this
    if isinstance(tree, (exp.Delete, exp.Update)) and isinstance(target, exp.Table):
        where = tree.args.get("where")
        source = target.sql(dialect="sqlite")
        suffix = " " + where.sql(dialect="sqlite") if where else ""
        count = execute_sql("SELECT COUNT(*) AS affected FROM " + source + suffix, uri)
        sample = execute_sql("SELECT * FROM " + source + suffix + " LIMIT 5", uri)
        if count["success"] and sample["success"]:
            rows = sample["result"]
            return details, {
                "estimated_rows": count["result"][0]["affected"],
                "sample_rows": rows,
                "sample_columns": list(rows[0]) if rows else [],
                "message": "Read-only preview; no changes have been executed.",
            }
    return details, {
        "estimated_rows": None,
        "sample_rows": [],
        "sample_columns": [],
        "message": "An exact affected-row estimate is unavailable; no changes have been executed.",
    }
