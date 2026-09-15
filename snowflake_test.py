import os
from tools import get_schema_json

uri = os.getenv("SNOWFLAKE_URI", "snowflake://<user>:<password>@<account>/<database>/<schema>?warehouse=<warehouse>")

res = get_schema_json(uri)
print(res)
