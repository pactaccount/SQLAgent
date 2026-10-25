"""SQLite execution with parsing, engine-enforced restrictions and bounded results."""

from contextlib import closing
import sqlite3
import time
from pathlib import Path
from sqlalchemy.engine import make_url
import sqlglot
from sqlglot import exp
from seaql.config import ROOT, MAX_ROWS, QUERY_SECONDS


def database_path(db_uri):
    url = make_url(db_uri)
    if url.drivername != "sqlite" or not url.database or url.query:
        raise ValueError("This build supports registered SQLite files only.")
    path = Path(url.database)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file() and url.database == "chinook.db":
        path = ROOT / "data" / "chinook.db"
    path = path.resolve()
    if not path.is_file():
        raise ValueError("Database file does not exist.")
    return path


def connect_readonly(path):
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    db.execute("PRAGMA query_only=ON")
    db.execute("PRAGMA trusted_schema=OFF")
    return db


def get_schema_json(db_uri):
    try:
        with closing(connect_readonly(database_path(db_uri))) as db:
            names = [
                r[0]
                for r in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            tables = []
            for name in names:
                quoted = '"' + name.replace('"', '""') + '"'
                cols = [
                    {"name": r[1], "type": r[2], "primary_key": bool(r[5])}
                    for r in db.execute("PRAGMA table_info(" + quoted + ")")
                ]
                tables.append({"name": name, "columns": cols})
            if not tables:
                raise ValueError("Database contains no application tables.")
            return {"success": True, "tables": tables}
    except Exception as e:
        return {"success": False, "error": str(e)}


def classify_sql(sql):
    statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    if len(statements) != 1:
        raise ValueError("Exactly one SQL statement is required.")
    tree = statements[0]
    if isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        if any(
            isinstance(
                n,
                (
                    exp.Insert,
                    exp.Update,
                    exp.Delete,
                    exp.Create,
                    exp.Drop,
                    exp.Alter,
                    exp.Command,
                    exp.Into,
                ),
            )
            for n in tree.walk()
        ):
            raise ValueError("Unsupported operation inside query.")
        return "read"
    if isinstance(
        tree, (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter)
    ):
        return "write"
    raise ValueError(
        "Only SELECT queries and reviewed data/schema changes are supported."
    )


def execute_sql(sql, db_uri, bypass_approval=False):
    db = None
    try:
        kind = classify_sql(sql)
        if kind == "write" and not bypass_approval:
            return {
                "success": True,
                "requires_approval": True,
                "result": None,
                "message": "Query flagged for review before execution.",
            }
        path = database_path(db_uri)
        # Never permit approved writes to the source dataset.
        if (
            kind == "write"
            and (ROOT / "olist.sqlite").exists()
            and path.samefile(ROOT / "olist.sqlite")
        ):
            raise ValueError(
                "The source Olist database is protected. Use an uploaded working copy for writes."
            )
        db = (
            connect_readonly(path)
            if kind == "read"
            else sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)
        )
        started = time.monotonic()
        db.set_progress_handler(
            lambda: int(time.monotonic() - started > QUERY_SECONDS), 1000
        )
        if kind == "read":
            allowed = {
                sqlite3.SQLITE_SELECT,
                sqlite3.SQLITE_READ,
                sqlite3.SQLITE_FUNCTION,
                sqlite3.SQLITE_RECURSIVE,
            }

            def authorize(action, a, b, c, d):
                if action == sqlite3.SQLITE_FUNCTION and (b or "").lower() in {
                    "load_extension",
                    "readfile",
                    "writefile",
                }:
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

            db.set_authorizer(authorize)
        else:
            # Reviewed writes still cannot attach databases, execute PRAGMAs or load extensions.
            denied = {
                sqlite3.SQLITE_ATTACH,
                sqlite3.SQLITE_DETACH,
                sqlite3.SQLITE_PRAGMA,
            }

            def authorize(action, a, b, c, d):
                if action in denied or (
                    action == sqlite3.SQLITE_FUNCTION
                    and (b or "").lower() in {"load_extension", "readfile", "writefile"}
                ):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            db.set_authorizer(authorize)
        cursor = db.execute(sql)
        if cursor.description:
            names = [c[0] for c in cursor.description]
            if len(set(names)) != len(names):
                raise ValueError("Use unique column aliases in the result.")
            rows = cursor.fetchmany(MAX_ROWS + 1)
            truncated = len(rows) > MAX_ROWS
            result = [dict(zip(names, r)) for r in rows[:MAX_ROWS]]
        else:
            truncated = False
            result = [{"status": "Success", "rows_affected": cursor.rowcount}]
        db.commit()
        return {
            "success": True,
            "requires_approval": False,
            "result": result,
            "truncated": truncated,
            "row_limit": MAX_ROWS,
        }
    except Exception as e:
        if db:
            db.rollback()
        return {"success": False, "error": str(e), "requires_approval": False}
    finally:
        if db:
            db.close()


def get_schema_for_query(query, tenant_id, db_uri=None):
    if not db_uri:
        raise ValueError("A registered database connection is required.")
    result = get_schema_json(db_uri)
    if not result["success"]:
        raise ValueError(result["error"])
    # Full schema is intentional for small databases: no embedding service or lost join tables.
    return "\n".join(
        t["name"]
        + "("
        + ", ".join(c["name"] + " " + c["type"] for c in t["columns"])
        + ")"
        for t in result["tables"]
    )
