"""Independent read-only reference execution and strict result comparison."""

from contextlib import closing
import math
import sqlite3
import time
from olist_cases import ROOT


def execute(sql, seconds=20):
    started = time.perf_counter()
    with closing(
        sqlite3.connect((ROOT / "olist.sqlite").as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.execute("PRAGMA query_only=ON")
        allowed = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
            sqlite3.SQLITE_RECURSIVE,
        }

        def authorize(action, arg1, arg2, database, trigger):
            if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in {
                "load_extension",
                "writefile",
                "readfile",
            }:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

        db.set_authorizer(authorize)
        db.set_progress_handler(
            lambda: int(time.perf_counter() - started > seconds), 10000
        )
        cursor = db.execute(sql)
        rows = cursor.fetchmany(10001)
        if len(rows) > 10000:
            raise ValueError("Result exceeds 10,000-row benchmark limit")
        return rows


def equal_rows(actual, expected):
    # Output columns must follow the requested/reference order. Row order is ignored;
    # top-N membership is still checked. Numeric tolerance permits presentation rounding.
    if len(actual) != len(expected):
        return False

    def key(row):
        return tuple((type(v).__name__, str(v)) for v in row)

    def cell(a, b):
        if isinstance(a, (float, int)) and isinstance(b, (float, int)):
            return math.isclose(a, b, rel_tol=1e-5, abs_tol=0.005)
        return a == b

    # Group by text/NULL cells so numeric sort differences cannot misalign rows.
    def grouping(row):
        return tuple(
            (i, str(v)) for i, v in enumerate(row) if not isinstance(v, (int, float))
        )

    groups = {}
    for r in expected:
        groups.setdefault(grouping(r), []).append(r)
    for r in actual:
        candidates = groups.get(grouping(r), [])
        found = next(
            (
                i
                for i, e in enumerate(candidates)
                if len(r) == len(e) and all(cell(a, b) for a, b in zip(r, e))
            ),
            None,
        )
        if found is None:
            return False
        candidates.pop(found)
    return True
