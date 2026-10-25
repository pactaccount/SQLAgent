"""Offline model benchmark; generated SQL runs on a read-only, bounded connection."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
from datetime import datetime, timezone

from olist_cases import ROOT, POLICY, cases


def execute(sql, seconds=20):
    started=time.perf_counter()
    with sqlite3.connect((ROOT/'olist.sqlite').as_uri()+'?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        allowed={sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ,sqlite3.SQLITE_FUNCTION,sqlite3.SQLITE_RECURSIVE}
        def authorize(action, arg1, arg2, database, trigger):
            if action == sqlite3.SQLITE_FUNCTION and (arg2 or '').lower() in {'load_extension','writefile','readfile'}:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
        db.set_authorizer(authorize)
        db.set_progress_handler(lambda: int(time.perf_counter()-started>seconds),10000)
        cursor=db.execute(sql)
        rows=cursor.fetchmany(10001)
        if len(rows)>10000:
            raise ValueError('Result exceeds 10,000-row benchmark limit')
        return rows


def equal_rows(actual, expected):
    # Output columns must follow the requested/reference order. Row order is ignored;
    # top-N membership is still checked. Numeric tolerance permits presentation rounding.
    if len(actual)!=len(expected): return False
    def key(row): return tuple((type(v).__name__,str(v)) for v in row)
    def cell(a,b):
        if isinstance(a,(float,int)) and isinstance(b,(float,int)):
            return math.isclose(a,b,rel_tol=1e-5,abs_tol=0.005)
        return a==b
    # Group by text/NULL cells so numeric sort differences cannot misalign rows.
    def grouping(row):
        return tuple((i,str(v)) for i,v in enumerate(row) if not isinstance(v,(int,float)))
    groups={}
    for r in expected: groups.setdefault(grouping(r),[]).append(r)
    for r in actual:
        candidates=groups.get(grouping(r),[])
        found=next((i for i,e in enumerate(candidates) if len(r)==len(e) and all(cell(a,b) for a,b in zip(r,e))),None)
        if found is None: return False
        candidates.pop(found)
    return True


def schema():
    with sqlite3.connect((ROOT/'olist.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        return '\n'.join(r[0] for r in db.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name"))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--validate-only',action='store_true')
    parser.add_argument('--limit',type=int,default=30)
    parser.add_argument('--output',default='artifacts/baseline/base.json')
    args=parser.parse_args()
    dataset=cases()
    references={c['id']:execute(c['reference_sql']) for c in dataset if c['reference_sql']}
    if args.validate_only:
        for c in dataset:
            print(c['id'],f"{len(references[c['id']])} rows" if c['reference_sql'] else 'clarification')
        print('All 26 reference queries execute. No model loaded.')
        return
    from mlx_lm import load,generate
    from mlx_lm.sample_utils import make_sampler
    model_path=ROOT/'models/qwen2.5-coder-7b-instruct-4bit'
    model,tokenizer=load(str(model_path))
    system=("You are a SQLite analyst. Return ONLY JSON: "
            '{"action":"sql","sql":"SELECT ..."} or '
            '{"action":"clarify","question":"..."}. '
            'Never modify the database. Select only columns requested, in their requested order. '
            'Ask clarification when the question cannot be answered without inventing definitions.\n'
            +POLICY+'\nSchema:\n'+schema())
    target=ROOT/args.output
    target.parent.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((ROOT/'artifacts/setup/model_manifest.json').read_text())
    db_hash=hashlib.file_digest((ROOT/'olist.sqlite').open('rb'),'sha256').hexdigest()
    report={'started_at':datetime.now(timezone.utc).isoformat(),'model':manifest,
            'database_sha256':db_hash,'benchmark_sha256':hashlib.sha256(json.dumps(dataset,sort_keys=True).encode()).hexdigest(),
            'prompt_sha256':hashlib.sha256(system.encode()).hexdigest(),
            'settings':{'temperature':0,'max_tokens':1536},
            'scope':'Direct local model benchmark, not the deployed agent. Fixed-schema small benchmark; not cross-schema generalization.',
            'results':[]}
    for c in dataset[:args.limit]:
        print(f"Running {c['id']}...",flush=True)
        result={k:v for k,v in c.items() if k!='reference_sql'}
        started=time.perf_counter()
        try:
            prompt=tokenizer.apply_chat_template([{'role':'system','content':system},{'role':'user','content':c['question']}],tokenize=False,add_generation_prompt=True)
            answer=generate(model,tokenizer,prompt=prompt,max_tokens=1536,sampler=make_sampler(temp=0),verbose=False)
            result['generation_seconds']=time.perf_counter()-started
            result['raw_output']=answer
            start=answer.find('{')
            if start<0: raise ValueError('No JSON object returned')
            parsed,_=json.JSONDecoder().raw_decode(answer[start:])
            result['parsed']=parsed
            result['action_correct']=parsed.get('action')==c['expected_action']
            if parsed.get('action')=='sql':
                t=time.perf_counter()
                rows=execute(parsed['sql'])
                result.update(sql_executable=True,execution_seconds=time.perf_counter()-t,actual_rows=rows)
                result['correct']=c['expected_action']=='sql' and equal_rows(rows,references[c['id']])
                result['status']='correct' if result['correct'] else 'incorrect'
            else:
                result['clarification_action_correct']=c['expected_action']=='clarify' and bool(parsed.get('question','').strip())
                result['status']='needs_human_review' if result['clarification_action_correct'] else 'incorrect'
                result['correct']=False
        except Exception as error:
            result.update(status='error',error=f'{type(error).__name__}: {error}',correct=False)
        result['total_seconds']=time.perf_counter()-started
        report['results'].append(result)
        sql_results=[r for r in report['results'] if r['expected_action']=='sql']
        report['summary']={'completed':len(report['results']),'planned':len(dataset[:args.limit]),
            'sql_correct':sum(r['correct'] for r in sql_results),'sql_total':len(sql_results),
            'sql_execution_accuracy':sum(r['correct'] for r in sql_results)/len(sql_results) if sql_results else None,
            'errors':sum(r['status']=='error' for r in report['results']),
            'clarifications_requiring_review':sum(r['status']=='needs_human_review' for r in report['results'])}
        temporary=target.with_suffix('.tmp')
        temporary.write_text(json.dumps(report,indent=2)+'\n')
        temporary.replace(target)
        print(c['id'],result['status'],flush=True)
    print(json.dumps(report['summary'],indent=2))
    print('Saved:',target)


if __name__=='__main__': main()
