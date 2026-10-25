import sqlite3
import pytest


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "sample.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE orders(order_id TEXT, order_status TEXT, price REAL)")
        db.executemany(
            "INSERT INTO orders VALUES(?,?,?)",
            [("a", "delivered", 10), ("b", "delivered", 20), ("c", "canceled", 5)],
        )
    return "sqlite:///" + str(path)
