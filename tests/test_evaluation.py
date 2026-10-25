"""The agent evaluator must score final results and keep failures in denominators."""
import importlib.util
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'eval'))
from run_agent_eval import evaluate_case, summary, load_cases
from model_gateway import ModelServiceError


def test_correct_rows_and_mismatches():
    case={'id':'X','question':'count','expected_action':'sql','reference_sql':'SELECT 3'}
    good=evaluate_case(case,[(3,)],lambda *args:{'execution_result':[{'n':3}]})
    wrong=evaluate_case(case,[(3,)],lambda *args:{'execution_result':[{'n':2}]})
    assert good['correct'] is True and wrong['correct'] is False
    report=summary([good,wrong],2)
    assert report['result_accuracy']==0.5 and report['execution_success_rate']==1


def test_provider_failure_stays_in_accuracy_denominator():
    def fail(*args):raise ModelServiceError('Rate limit',429)
    case={'id':'X','question':'count','expected_action':'sql','reference_sql':'SELECT 3'}
    failed=evaluate_case(case,[(3,)],fail)
    report=summary([failed],30)
    assert report['result_accuracy']==0 and report['provider_errors']==1
    assert not report['complete']


def test_clarification_requires_review_not_automatic_credit():
    case={'id':'X','question':'best','expected_action':'clarify','reference_sql':None}
    result=evaluate_case(case,None,lambda *args:{'clarification':True,'final_answer':'Which metric?'})
    assert result['correct'] is None and result['status']=='needs_human_review'


def test_truncation_cannot_pass_result_equivalence():
    case={'id':'X','question':'count','expected_action':'sql','reference_sql':'SELECT 3'}
    result=evaluate_case(case,[(3,)],lambda *args:{'execution_result':[{'n':3}],'truncated':True})
    assert not result['correct']


def test_reserved_final_questions_not_in_initial_agent_evaluation():
    dataset=load_cases()
    assert len(dataset)==30 and all(c['id'].startswith('Q') for c in dataset)
