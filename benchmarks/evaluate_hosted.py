"""Small, fixed result-equivalence check for the public SeaQL demo.

Runs nine read-only questions against the MIT-licensed Chinook sample database.
This calls the configured hosted model; run intentionally, not in CI.
"""

import argparse
import hashlib
import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests


def normalized(value):
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    return str(value).strip().casefold()


def equivalent(expected, actual):
    if len(expected) != len(actual):
        return False
    return all(
        sorted(map(normalized, expected_row)) == sorted(map(normalized, actual_row.values()))
        for expected_row, actual_row in zip(expected, actual)
    )


def run(base_url, db_path, output):
    cases = json.loads((Path(__file__).parent / "chinook_cases.json").read_text())
    db_path = Path(db_path)
    with sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True) as db:
        expected = {case["id"]: db.execute(case["reference_sql"]).fetchall() for case in cases}
    tenant = "resume-eval-" + uuid.uuid4().hex[:12]
    with db_path.open("rb") as db_file:
        response = requests.post(
            base_url.rstrip("/") + "/upload_db",
            files={"file": (tenant + ".db", db_file, "application/octet-stream")},
            timeout=150,
        )
    response.raise_for_status()
    db_uri = response.json()["db_uri"]
    rows = []
    for case in cases:
        start = time.monotonic()
        try:
            response = requests.post(
                base_url.rstrip("/") + "/chat",
                json={"query": case["question"], "tenant_id": tenant, "db_uri": db_uri},
                timeout=150,
            )
            payload = response.json()
            actual = payload.get("execution_result") or []
            detail = str(payload.get("detail") or "")
            rate_limited = response.status_code == 429 or (
                response.status_code == 500 and ("429" in detail or "quota exceeded" in detail.lower())
            )
            correct = response.ok and equivalent(expected[case["id"]], actual)
            row = {
                "id": case["id"], "question": case["question"],
                "expected_rows": expected[case["id"]], "actual_rows": actual,
                "generated_sql": payload.get("sql_query"), "http_status": response.status_code,
                "correct_result": correct, "rate_limited": rate_limited,
                "latency_seconds": round(time.monotonic() - start, 2),
                "error": "provider_rate_limited" if rate_limited else ("backend_error" if not response.ok else None),
            }
        except Exception as exc:
            row = {"id": case["id"], "question": case["question"], "correct_result": False,
                   "latency_seconds": round(time.monotonic() - start, 2),
                   "error": type(exc).__name__}
        rows.append(row)
        print(f"{case['id']}: {'PASS' if row['correct_result'] else 'FAIL'} ({row['latency_seconds']}s)", flush=True)
    completed = [row for row in rows if row.get("http_status") == 200]
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url, "dataset": "Chinook SQLite, 11 tables",
        "dataset_sha256": hashlib.sha256(db_path.read_bytes()).hexdigest(),
        "protocol": "fixed nine-question result equivalence; read-only; single run; no tuning on these questions",
        "correct": sum(row["correct_result"] for row in rows), "total": len(rows),
        "completed": len(completed), "correct_on_completed": sum(row["correct_result"] for row in completed),
        "rate_limited": sum(row.get("rate_limited", False) for row in rows),
        "per_question": rows,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['correct']}/{report['total']} correct; report: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://seaql.onrender.com")
    parser.add_argument("--db", default="chinook.db")
    parser.add_argument("--output", default="benchmarks/results/hosted_2026-10-22.json")
    args = parser.parse_args()
    run(args.base_url, args.db, args.output)
