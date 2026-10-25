"""Persistent local connection catalog, approvals, history, cache and request records."""
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from settings import DATA


class RuntimeStore:
    def __init__(self,path=None):
        self.path=path or DATA/'catalog.sqlite'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS connections(id TEXT PRIMARY KEY,owner TEXT,uri TEXT,label TEXT);
            CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY,owner TEXT,connection_id TEXT,sql TEXT,expires REAL,status TEXT,outcome TEXT);
            CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,sql TEXT,expires REAL);
            CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY,owner TEXT,conversation TEXT,connection_id TEXT,role TEXT,content TEXT);
            CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY,created REAL,owner TEXT,connection_id TEXT,seconds REAL,payload TEXT);
            ''')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10)
        db.row_factory=sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback();raise
        finally:db.close()
    def register(self,owner,uri,label):
        key=hashlib.sha256((owner+'\0'+uri).encode()).hexdigest()[:32]
        with self.db() as db:db.execute('INSERT OR REPLACE INTO connections VALUES(?,?,?,?)',(key,owner,uri,label))
        return key
    def connection(self,owner,key):
        with self.db() as db:r=db.execute('SELECT * FROM connections WHERE id=? AND owner=?',(key,owner)).fetchone()
        if not r:raise ValueError('Connection not found in this browser workspace.')
        return dict(r)
    def connections(self,owner):
        with self.db() as db:return [dict(r) for r in db.execute('SELECT id,label FROM connections WHERE owner=? ORDER BY label',(owner,))]
    def approval(self,owner,connection,sql):
        key=secrets.token_urlsafe(32)
        with self.db() as db:db.execute('INSERT INTO approvals VALUES(?,?,?,?,?,?,?)',(key,owner,connection,sql,time.time()+600,'pending',None))
        return key
    def consume(self,owner,key,status):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            r=db.execute("SELECT * FROM approvals WHERE id=? AND owner=? AND status='pending' AND expires>?",(key,owner,time.time())).fetchone()
            if not r:raise ValueError('Approval expired, unavailable, or already used.')
            db.execute('UPDATE approvals SET status=? WHERE id=?',(status,key))
            return dict(r)
    def finish(self,key,status,outcome):
        with self.db() as db:db.execute('UPDATE approvals SET status=?,outcome=? WHERE id=?',(status,json.dumps(outcome),key))
    def cached(self,key):
        with self.db() as db:r=db.execute('SELECT sql FROM cache WHERE key=? AND expires>?',(key,time.time())).fetchone()
        return r[0] if r else None
    def cache(self,key,sql):
        with self.db() as db:db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(key,sql,time.time()+3600))
    def history(self,owner,conversation,connection):
        with self.db() as db:
            rows=db.execute('SELECT role,content FROM history WHERE owner=? AND conversation=? AND connection_id=? ORDER BY id DESC LIMIT 12',(owner,conversation,connection)).fetchall()
        return [dict(r) for r in reversed(rows)]
    def record_turn(self,owner,conversation,connection,question,answer):
        with self.db() as db:
            for role,content in [('user',question),('assistant',answer)]:
                db.execute('INSERT INTO history(owner,conversation,connection_id,role,content) VALUES(?,?,?,?,?)',(owner,conversation,connection,role,content))
    def record_request(self,owner,connection,seconds,payload):
        with self.db() as db:db.execute('INSERT INTO requests(created,owner,connection_id,seconds,payload) VALUES(?,?,?,?,?)',(time.time(),owner,connection,seconds,json.dumps(payload)))
