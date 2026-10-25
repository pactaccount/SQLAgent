import sqlite3
import pytest
import tools


@pytest.mark.parametrize('sql',[
    'PRAGMA user_version=42',"ATTACH DATABASE ':memory:' AS extra",'SELECT 1; SELECT 2',
    "SELECT load_extension('x')",'VACUUM','BEGIN','COMMIT'])
def test_unsupported_statements_do_not_execute(database,sql):
    assert not tools.execute_sql(sql,database)['success']
    with sqlite3.connect(tools.database_path(database)) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==3


def test_literal_keyword_is_not_a_write(database):
    result=tools.execute_sql("SELECT 'update' AS label",database)
    assert result['success'] and not result['requires_approval']


def test_cte_read_and_reviewed_write(database):
    assert tools.execute_sql('WITH x AS (SELECT COUNT(*) AS n FROM orders) SELECT n FROM x',database)['result']==[{'n':3}]
    assert tools.execute_sql('DELETE FROM orders',database)['requires_approval']
    assert tools.execute_sql("DELETE FROM orders WHERE order_status='canceled'",database,True)['success']
    assert tools.execute_sql('SELECT COUNT(*) AS n FROM orders',database)['result']==[{'n':2}]


def test_timeout(database,monkeypatch):
    monkeypatch.setattr(tools,'QUERY_SECONDS',0)
    result=tools.execute_sql('WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<1000000) SELECT SUM(x) FROM n',database)
    assert not result['success'] and 'interrupt' in result['error'].lower()


def test_missing_database_not_created(tmp_path):
    path=tmp_path/'absent.sqlite'
    assert not tools.get_schema_json('sqlite:///'+str(path))['success']
    assert not path.exists()
