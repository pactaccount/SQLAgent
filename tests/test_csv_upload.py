from fastapi.testclient import TestClient
import pytest
import seaql.api as service
import seaql.database as tools


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "DATA", tmp_path)
    return TestClient(service.app)


def upload(client, body, name="sales.csv"):
    return client.post("/upload_db", files={"file": (name, body, "text/csv")})


def test_csv_upload_connect_query_and_chat(client, monkeypatch):
    result = upload(
        client,
        b'product,quantity,price,postal_code\n"Red, large",2,10.5,00123\nBlue,3,20,00456\n',
    )
    assert result.status_code == 200
    data = result.json()
    assert data["table_name"] == "sales" and data["row_count"] == 2
    connection = {"tenant_id": "csv", "db_uri": data["db_uri"]}
    assert client.post("/connect", json=connection).json()["table_count"] == 1
    schema = client.post("/schema", json=connection).json()
    assert [(c["name"], c["type"]) for c in schema["tables"][0]["columns"]] == [
        ("product", "TEXT"),
        ("quantity", "INTEGER"),
        ("price", "REAL"),
        ("postal_code", "TEXT"),
    ]
    assert tools.execute_sql(
        "SELECT SUM(quantity) AS units, SUM(price) AS total FROM sales", data["db_uri"]
    )["result"] == [{"units": 5, "total": 30.5}]
    assert (
        tools.execute_sql(
            "SELECT postal_code FROM sales ORDER BY postal_code", data["db_uri"]
        )["result"][0]["postal_code"]
        == "00123"
    )

    def complete(messages):
        assert "Do not invent Olist-specific" in messages[0]["content"]
        assert "customers.customer_unique_id identifies" not in messages[0]["content"]
        return (
            '{"action":"sql","sql":"SELECT SUM(quantity) AS units FROM sales"}',
            "test-model",
        )

    monkeypatch.setattr("seaql.agent.complete", complete)
    answer = client.post("/chat", json={**connection, "query": "How many units?"})
    assert answer.status_code == 200 and answer.json()["execution_result"] == [
        {"units": 5}
    ]


def test_bom_nulls_mixed_types_and_identifiers(client):
    result = upload(
        client,
        '\ufeffItem name,amount,notes\nWidget,12,"hello\nworld"\nGadget,,ok\nOther,n/a,\n'.encode(),
        "2026 sales.CSV",
    )
    assert result.status_code == 200
    data = result.json()
    assert data["table_name"] == "data_2026_sales"
    rows = tools.execute_sql(
        'SELECT "Item name", amount, notes FROM data_2026_sales', data["db_uri"]
    )["result"]
    assert rows[0] == {"Item name": "Widget", "amount": "12", "notes": "hello\nworld"}
    assert rows[1]["amount"] is None and rows[2]["notes"] is None


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"a,b\n",
        b"a,a\n1,2\n",
        b"A,a\n1,2\n",
        b",b\n1,2\n",
        b"a,b\n1,2,3\n",
        b"a,b\n1\n",
        b'a,b\n"unterminated,2\n',
        b"a\n\xff\n",
    ],
)
def test_invalid_csv_rejected_and_files_cleaned(client, content):
    result = upload(client, content)
    assert result.status_code == 400
    assert not list(service.DATA.rglob("*.csv"))
    assert not list(service.DATA.rglob("*.sqlite"))


def test_csv_beyond_previous_field_and_column_caps(client):
    headers = [f"c{i}" for i in range(201)]
    values = ["x" * (1024 * 1024 + 1)] + ["1"] * 200
    content = (",".join(headers) + "\n" + ",".join(values) + "\n").encode()
    result = upload(client, content)
    assert result.status_code == 200
    assert result.json()["row_count"] == 1


def test_large_identifier_not_coerced_to_float(client):
    data = upload(client, b"id,value\n9223372036854775808,1e2\n").json()
    assert tools.execute_sql("SELECT * FROM sales", data["db_uri"])["result"] == [
        {"id": "9223372036854775808", "value": 100.0}
    ]
