"""Deterministic tests exercise the real graph without external model calls."""
import json
import pytest
import agent
from model_gateway import ModelServiceError


def outputs(monkeypatch,*responses):
    calls=[]
    it=iter(responses)
    def complete(messages):
        calls.append(messages)
        return next(it),'test-model'
    monkeypatch.setattr(agent,'complete',complete)
    return calls


def test_result_and_real_schema(monkeypatch,database):
    calls=outputs(monkeypatch,json.dumps({'action':'sql','sql':'SELECT COUNT(*) AS count FROM orders'}))
    state=agent.run_agent('count orders','test',database)
    assert state['execution_result']==[{'count':3}]
    assert 'order_status' in calls[0][0]['content']
    assert state['model_id']=='test-model'
    assert state['attempts'][0]['execution_success']


def test_retry_uses_failed_sql(monkeypatch,database):
    calls=outputs(monkeypatch,'{"action":"sql","sql":"SELECT missing FROM orders"}',
                  '{"action":"sql","sql":"SELECT SUM(price) AS total FROM orders"}')
    state=agent.run_agent('total','test',database)
    assert state['retry_count']==1
    assert state['execution_result']==[{'total':35.0}]
    assert 'SELECT missing FROM orders' in calls[1][-1]['content']
    assert len(state['attempts'])==2


def test_clarification_never_executes(monkeypatch,database):
    outputs(monkeypatch,'{"action":"clarify","question":"Which metric and year?"}')
    monkeypatch.setattr(agent,'execute_sql',lambda *args:pytest.fail('Clarification executed SQL'))
    state=agent.run_agent('best orders','test',database)
    assert state['clarification'] and state['sql_query']==''


def test_invalid_output_stops_after_three(monkeypatch,database):
    calls=outputs(monkeypatch,'not json','[]','{"action":"other"}')
    state=agent.run_agent('count','test',database)
    assert len(calls)==3 and state['retry_count']==3
    assert state['execution_result'] is None


def test_sql_parse_error_retries(monkeypatch,database):
    outputs(monkeypatch,'{"action":"sql","sql":"SELECT ("}',
            '{"action":"sql","sql":"SELECT 1 AS value"}')
    assert agent.run_agent('one','test',database)['execution_result']==[{'value':1}]


def test_approval_stops_execution(monkeypatch,database):
    outputs(monkeypatch,'{"action":"sql","sql":"DELETE FROM orders"}')
    state=agent.run_agent('delete','test',database)
    assert state['requires_approval'] and state['execution_result'] is None


def test_provider_error_is_not_sql_retry(monkeypatch,database):
    def fail(*args):raise ModelServiceError('Provider unavailable',429)
    monkeypatch.setattr(agent,'complete',fail)
    with pytest.raises(ModelServiceError):agent.run_agent('count','test',database)
