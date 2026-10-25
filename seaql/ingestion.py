"""Stream UTF-8 CSV into SQLite without loading the file into application memory."""

import csv
import math
from pathlib import Path
import re
import sqlite3
import sys

csv.field_size_limit(sys.maxsize)


def quoted(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def value_type(value):
    text = value.strip()
    if not text:
        return None
    # Keep postal codes, account identifiers, and integers outside SQLite's range as text.
    if re.fullmatch(r"[+-]?\d+", text):
        digits = text.lstrip("+-")
        if len(digits) > 1 and digits.startswith("0"):
            return "TEXT"
        return "INTEGER" if -(2**63) <= int(text) < 2**63 else "TEXT"
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?", text):
        return "REAL" if math.isfinite(float(text)) else "TEXT"
    return "TEXT"


def rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        yield from reader


def import_csv(source, destination, filename):
    source, destination = Path(source), Path(destination)
    try:
        iterator = rows(source)
        headers = next(iterator, None)
        if not headers:
            raise ValueError(
                "CSV is empty. Include a header row and at least one data row."
            )
        headers = [name.strip() for name in headers]
        if any(
            not name or any(ord(c) < 32 for c in name)
            for name in headers
        ):
            raise ValueError(
                "CSV column names must be nonempty, readable names."
            )
        if len({name.casefold() for name in headers}) != len(headers):
            raise ValueError("CSV column names must be unique (ignoring letter case).")
        types = [None] * len(headers)
        count = 0
        for line, row in enumerate(iterator, 2):
            if not row:  # Ignore physically empty lines, not empty cells.
                continue
            if len(row) != len(headers):
                raise ValueError(
                    f"CSV record {line} has {len(row)} fields; expected {len(headers)}."
                )
            count += 1
            for index, value in enumerate(row):
                candidate = value_type(value)
                if candidate is None:
                    continue
                current = types[index]
                if current is None:
                    types[index] = candidate
                elif current != candidate:
                    types[index] = (
                        "REAL"
                        if {current, candidate} <= {"INTEGER", "REAL"}
                        else "TEXT"
                    )
        if not count:
            raise ValueError("CSV must contain at least one data row after its header.")
        types = [kind or "TEXT" for kind in types]
        stem = Path(filename.replace("\\", "/")).stem
        table = re.sub(r"[^a-zA-Z0-9_]+", "_", stem).strip("_")[:60] or "csv_data"
        if table[0].isdigit() or table.lower().startswith("sqlite_"):
            table = "data_" + table
        with sqlite3.connect(destination) as db:
            db.execute(
                "CREATE TABLE "
                + quoted(table)
                + "("
                + ",".join(quoted(h) + " " + t for h, t in zip(headers, types))
                + ")"
            )
            insert = (
                "INSERT INTO "
                + quoted(table)
                + " VALUES ("
                + ",".join("?" for _ in headers)
                + ")"
            )
            batch = []
            iterator = rows(source)
            next(iterator)
            for row in iterator:
                if not row:
                    continue
                values = []
                for value, kind in zip(row, types):
                    if not value.strip():
                        values.append(None)
                    elif kind == "INTEGER":
                        values.append(int(value.strip()))
                    elif kind == "REAL":
                        values.append(float(value.strip()))
                    else:
                        values.append(value)
                batch.append(values)
                if len(batch) == 500:
                    db.executemany(insert, batch)
                    batch.clear()
            if batch:
                db.executemany(insert, batch)
        return {
            "table_name": table,
            "row_count": count,
            "columns": [{"name": h, "type": t} for h, t in zip(headers, types)],
        }
    except (UnicodeError, csv.Error) as error:
        raise ValueError(
            "CSV must be valid UTF-8, comma-separated text with correctly quoted fields."
        ) from error
