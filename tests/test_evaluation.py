"""The agent evaluator must score final results and keep failures in denominators."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
from run_agent_eval import evaluate_case, summary, load_cases
from seaql.model import ModelServiceError


def test_correct_rows_and_mismatches():
    case = {
        "id": "X",
        "question": "count",
        "expected_action": "sql",
        "reference_sql": "SELECT 3",
    }
    good = evaluate_case(case, [(3,)], lambda *args: {"execution_result": [{"n": 3}]})
    wrong = evaluate_case(case, [(3,)], lambda *args: {"execution_result": [{"n": 2}]})
    assert good["correct"] is True and wrong["correct"] is False
    report = summary([good, wrong], 2)
    assert report["result_accuracy"] == 0.5 and report["execution_success_rate"] == 1


def test_provider_failure_stays_in_accuracy_denominator():
    def fail(*args):
        raise ModelServiceError("Rate limit", 429)

    case = {
        "id": "X",
        "question": "count",
        "expected_action": "sql",
        "reference_sql": "SELECT 3",
    }
    failed = evaluate_case(case, [(3,)], fail)
    report = summary([failed], 30)
    assert report["result_accuracy"] == 0 and report["provider_errors"] == 1
    assert not report["complete"]


def test_clarification_requires_review_not_automatic_credit():
    case = {
        "id": "X",
        "question": "best",
        "expected_action": "clarify",
        "reference_sql": None,
    }
    result = evaluate_case(
        case,
        None,
        lambda *args: {"clarification": True, "final_answer": "Which metric?"},
    )
    assert result["correct"] is None and result["status"] == "needs_human_review"


def test_truncation_cannot_pass_result_equivalence():
    case = {
        "id": "X",
        "question": "count",
        "expected_action": "sql",
        "reference_sql": "SELECT 3",
    }
    result = evaluate_case(
        case, [(3,)], lambda *args: {"execution_result": [{"n": 3}], "truncated": True}
    )
    assert not result["correct"]


def test_reserved_final_questions_not_in_initial_agent_evaluation():
    dataset = load_cases()
    assert len(dataset) == 30 and all(c["id"].startswith("Q") for c in dataset)


import json
import shutil
import pytest
import run_agent_eval as evaluator


@pytest.mark.parametrize("suite", ["development", "holdout"])
def test_report_cli_after_package_move(tmp_path, monkeypatch, suite):
    """Exercise reference loading, source hashing and report writing without inference."""
    output = tmp_path / (suite + ".json")
    # Fresh CI checkouts do not contain the private/local Olist database.
    shutil.copytree(
        evaluator.ROOT / "seaql",
        tmp_path / "seaql",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (tmp_path / "olist.sqlite").write_bytes(
        b"hash fixture; reference execution is injected"
    )
    monkeypatch.setattr(evaluator, "ROOT", tmp_path)
    monkeypatch.setattr(evaluator, "execute", lambda sql: [(1,)])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_agent_eval.py",
            "--suite",
            suite,
            "--limit",
            "1",
            "--output",
            str(output),
        ],
    )
    monkeypatch.setattr(
        evaluator,
        "evaluate_case",
        lambda case, reference: {
            "id": case["id"],
            "expected_action": case["expected_action"],
            "correct": True,
            "execution_success": True,
            "status": "correct",
            "seconds": 0.1,
        },
    )
    evaluator.main()
    report = json.loads(output.read_text())
    assert report["summary"]["complete"]
    assert len(report["source_sha256"]) == 4
    assert all(name.startswith("seaql/") for name in report["source_sha256"])
