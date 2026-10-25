"""Evaluate the same run_agent entry point used by the web API. No local model needed."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import math
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from seaql.agent import run_agent, PROMPT_VERSION
from seaql.policy import POLICY, CHECKLIST
from seaql.model import ModelServiceError, model_config
from olist_cases import cases
from comparison import execute, equal_rows


def load_cases():
    dataset = cases()
    # Explicit output contracts remove the original reference-projection ambiguity.
    for c in dataset:
        if c["id"] == "Q05":
            c["question"] = (
                "What are the 5 highest-priced individual items sold in delivered orders? Return product_id and price."
            )
        if c["id"] == "Q24":
            c["question"] = (
                "For repeat buyers (more than one lifetime order) and one-time buyers, what percentage of review rows have a score of 4 or 5? Return cohort and percentage."
            )
    return dataset


def evaluate_case(case, reference, runner=run_agent):
    result = {k: v for k, v in case.items() if k != "reference_sql"}
    started = time.perf_counter()
    try:
        state = runner(
            case["question"], "evaluation", "sqlite:///" + str(ROOT / "olist.sqlite")
        )
        rows = state.get("execution_result")
        result.update(
            sql=state.get("sql_query", ""),
            answer=state.get("final_answer", ""),
            rows=rows,
            attempts=state.get("attempts", []),
            errors=state.get("error_traces", []),
            retry_count=state.get("retry_count", 0),
            model_id=state.get("model_id", "unknown"),
            clarification=state.get("clarification", False),
            truncated=state.get("truncated", False),
            requires_approval=state.get("requires_approval", False),
        )
        result["execution_success"] = rows is not None
        result["correct"] = bool(
            case["expected_action"] == "sql"
            and rows is not None
            and not result["truncated"]
            and equal_rows([list(r.values()) for r in rows], reference)
        )
        if case["expected_action"] == "clarify":
            result["status"] = (
                "needs_human_review" if result["clarification"] else "incorrect_action"
            )
            result["correct"] = None
        else:
            result["status"] = (
                "correct"
                if result["correct"]
                else "clarified_answerable"
                if result["clarification"]
                else "incorrect_result"
                if rows is not None
                else "execution_failed"
            )
        # This is an observable execution-error label, not a general hallucination score.
        result["schema_reference_errors"] = [
            e
            for e in result["errors"]
            if "no such column" in e.lower() or "no such table" in e.lower()
        ]
        result["unsupported_assumptions_review"] = "pending"
    except ModelServiceError as e:
        result.update(
            status="provider_error",
            error=str(e),
            provider_status=e.status_code,
            correct=False,
            execution_success=False,
        )
    except Exception as e:
        result.update(
            status="system_error",
            error=f"{type(e).__name__}: {e}",
            correct=False,
            execution_success=False,
        )
    result["seconds"] = time.perf_counter() - started
    return result


def summary(results, planned):
    sql = [r for r in results if r["expected_action"] == "sql"]
    successful = sum(r.get("execution_success", False) for r in sql)
    correct = sum(r.get("correct") is True for r in sql)
    times = sorted(r["seconds"] for r in results)
    return {
        "completed": len(results),
        "planned": planned,
        "complete": len(results) == planned,
        "sql_tasks": len(sql),
        "correct_results": correct,
        "result_accuracy": correct / len(sql) if sql else None,
        "successful_executions": successful,
        "execution_success_rate": successful / len(sql) if sql else None,
        "provider_errors": sum(r["status"] == "provider_error" for r in results),
        "system_errors": sum(r["status"] == "system_error" for r in results),
        "clarification_cases": sum(r["expected_action"] == "clarify" for r in results),
        "clarifications_pending_review": sum(
            r["status"] == "needs_human_review" for r in results
        ),
        "median_seconds": statistics.median(times) if times else None,
        "p95_seconds_nearest_rank": times[max(0, math.ceil(0.95 * len(times)) - 1)]
        if times
        else None,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--suite", choices=["development", "holdout"], default="development")
    p.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate all reference queries; makes no model calls.",
    )
    p.add_argument("--limit", type=int, default=30)
    p.add_argument(
        "--output", help="New report path; existing reports are never overwritten."
    )
    args = p.parse_args()
    if not 1 <= args.limit <= 30:
        p.error("--limit must be between 1 and 30")
    if args.suite == "holdout":
        from holdout_cases import cases as holdout_cases

        dataset = holdout_cases()
    else:
        dataset = load_cases()
    references = {
        c["id"]: execute(c["reference_sql"]) for c in dataset if c["reference_sql"]
    }
    if args.validate_only:
        print(
            f"Validated {len(references)} reference queries and {len(dataset) - len(references)} clarification cases. No API calls made."
        )
        return
    selected = dataset[: args.limit]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / (args.output or f"artifacts/agent_eval/{stamp}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the path before spending model calls, including across concurrent runs.
    with output.open("x") as f:
        f.write("{}\n")
    with (ROOT / "olist.sqlite").open("rb") as f:
        db_hash = hashlib.file_digest(f, "sha256").hexdigest()
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_version": "olist-agent-v2"
        if args.suite == "development"
        else "olist-holdout-v1",
        "scope": "Application run_agent workflow, one NVIDIA API model, no cache; not hosted HTTP latency.",
        "model_config": model_config(),
        "prompt_version": PROMPT_VERSION,
        "policy_sha256": hashlib.sha256(
            (POLICY + "\n" + CHECKLIST).encode()
        ).hexdigest(),
        "database_sha256": db_hash,
        "dataset_sha256": hashlib.sha256(
            json.dumps(dataset, sort_keys=True).encode()
        ).hexdigest(),
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in [
                "seaql/agent.py",
                "seaql/database.py",
                "seaql/model.py",
                "seaql/policy.py",
            ]
        },
        "suite": args.suite,
        "settings": {"temperature": 0, "max_tokens": 1536, "max_failed_attempts": 3},
        "results": [],
    }
    for c in selected:
        print(f"Running {c['id']}...", flush=True)
        result = evaluate_case(c, references.get(c["id"]))
        report["results"].append(result)
        report["summary"] = summary(report["results"], len(selected))
        temp = output.with_suffix(".tmp")
        temp.write_text(json.dumps(report, indent=2) + "\n")
        temp.replace(output)
        print(c["id"], result["status"], flush=True)
        # A bad key, unavailable model or provider outage should not burn the whole run.
        if result["status"] == "provider_error":
            print(
                "Stopped after provider failure; report is marked incomplete. Resolve access before retrying.",
                flush=True,
            )
            break
    print(json.dumps(report["summary"], indent=2))
    print("Saved:", output)


if __name__ == "__main__":
    main()
