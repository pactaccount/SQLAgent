from tools import get_schema_json
import os

usernames = ["Abhinav", "ABHINAV", "abhinav"]
password = os.getenv("SNOWFLAKE_TEST_PASSWORD", "REPLACE_ME")
account = os.getenv("SNOWFLAKE_TEST_ACCOUNT", "REPLACE_ME")

for user in usernames:
    print(f"Testing with username: {user}")
    uri = f"snowflake://{user}:{password}@{account}/FIRST/PUBLIC?warehouse=SALES"
    res = get_schema_json(uri)
    if res.get("success"):
        print(f"SUCCESS with {user}!")
        print(res)
        break
    else:
        print(f"Failed with {user}: {res.get('error')[:150]}")
