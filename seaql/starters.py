"""
Starter questions derived from a database's real schema.

A beginner staring at an empty chat box does not know what to ask. These
questions are generated from the tables and columns that actually exist, so
they provide plausible starting points and show what the data contains. Their
generated answers still require the same execution and correctness checks.
"""

import re
from typing import Optional

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# Column-name hints. These are matched on word boundaries, not as raw
# substrings - "country" contains "count", and a naive substring match would
# decide that a text column is a measure.
_MEASURE_HINTS = (
    "total",
    "amount",
    "price",
    "cost",
    "revenue",
    "profit",
    "quantity",
    "qty",
    "count",
    "value",
    "balance",
    "salary",
    "hours",
    "duration",
    "score",
    "rating",
    "weight",
    "length",
    "size",
    "sales",
    "spend",
)

_CATEGORY_HINTS = (
    "name",
    "title",
    "category",
    "genre",
    "type",
    "status",
    "country",
    "state",
    "city",
    "region",
    "department",
    "artist",
    "album",
    "customer",
    "product",
    "label",
    "group",
    "kind",
    "class",
    "tier",
    "grade",
)

_TIME_HINTS = (
    "date",
    "time",
    "year",
    "month",
    "created",
    "updated",
    "birth",
    "hired",
    "released",
    "invoice",
    "order",
    "purchased",
    "timestamp",
)

_SEARCH_HINTS = ("email", "address", "phone", "description", "comment", "note")

# Tokens that mark a column as an identifier rather than a category.
_ID_TOKENS = ("id", "code", "key", "uuid", "guid")


def humanize(name: str) -> str:
    """Turn a column or table name into something a person can read."""
    text = _CAMEL_BOUNDARY.sub(" ", name)
    text = text.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def pluralize(word: str) -> str:
    """Naive but adequate English pluralisation for table labels."""
    if not word:
        return word
    lower = word.lower()
    if lower.endswith("y") and len(lower) > 1 and lower[-2] not in "aeiou":
        return word[:-1] + "ies"
    if lower.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    return word + "s"


def _tokens(name: str) -> list:
    """Split an identifier into lowercase word tokens."""
    return [t for t in re.split(r"[^A-Za-z0-9]+", humanize(name).lower()) if t]


def _matches_hint(name: str, hints: tuple) -> bool:
    """True if any hint word appears as a whole token in the name."""
    tokens = set(_tokens(name))
    for hint in hints:
        if hint in tokens:
            return True
        # A hint can also match a prefix of a token, e.g. "quantity" for
        # "qty" is handled above, but "genr" style typos are not needed.
    return False


def _is_id_column(name: str) -> bool:
    """True for identifier columns like CustomerId or InvoiceNo."""
    tokens = _tokens(name)
    if not tokens:
        return False
    last = tokens[-1]
    return last in _ID_TOKENS or (len(last) > 1 and last.endswith("id"))


def _is_numeric_type(type_string: str) -> bool:
    """True when a SQL type holds a number."""
    lowered = type_string.lower()
    return any(
        token in lowered
        for token in (
            "int",
            "num",
            "decimal",
            "float",
            "double",
            "real",
            "money",
            "bigint",
        )
    )


def _pick_column(
    columns: list, hints: tuple, types: dict, require_numeric: bool = False
):
    """Return the first column whose name matches one of the hint words."""
    for column in columns:
        if require_numeric and not _is_numeric_type(types.get(column, "")):
            continue
        if _matches_hint(column, hints):
            return column
    return None


def _metric_phrase(measure: str) -> str:
    """
    The measure as it reads inside a sentence, e.g. "Total" or "unit price".
    A column literally named "Total" must not become "the total total".
    """
    label = humanize(measure).lower()
    if label.startswith("total "):
        return label
    if label == "total":
        return "total"
    return f"total {label}"


def _build_question(table: str, columns: list, types: dict) -> Optional[str]:
    """Compose one natural question for a table, or None if it has no columns."""
    if not columns:
        return None

    table_label = humanize(table)
    plural = pluralize(table_label)

    # A measure must actually hold a number, otherwise "the total country"
    # is nonsense.
    measure = _pick_column(columns, _MEASURE_HINTS, types, require_numeric=True)
    category = _pick_column(columns, _CATEGORY_HINTS, types)
    time_col = _pick_column(columns, _TIME_HINTS, types)

    # An id column is not a useful thing to group by for a beginner.
    if category and _is_id_column(category):
        category = None

    # A metric per category is the single most useful question shape.
    if measure and category and measure != category:
        return f"What is the {_metric_phrase(measure)} for each {humanize(category).lower()}?"

    # A trend over time.
    if time_col and measure:
        return (
            f"How has the {_metric_phrase(measure)} changed over time in {table_label}?"
        )

    # A count of the rows.
    if any(_is_id_column(c) for c in columns) or len(columns) == 1:
        return f"How many {plural.lower()} are there?"

    # A listing of distinct values.
    if category:
        return (
            f"List the distinct {humanize(category).lower()} values in {table_label}."
        )

    # A plain listing.
    if len(columns) == 1:
        return f"Show all values of {humanize(columns[0]).lower()} in {table_label}."

    return f"Show me a sample of rows from {table_label}."


def generate_starter_questions(schema: dict, limit: int = 6) -> list:
    """
    Return a list of starter questions for a schema.

    Input is the payload from seaql.database.get_schema_json():
        {"success": True, "tables": [{"name": ..., "columns": [{"name","type"}]}]}

    Each question is returned with the table it came from, so the UI can show
    which part of the database it will explore.
    """
    if not schema or not schema.get("success"):
        return []

    questions = []
    seen = set()

    for table in schema.get("tables", []):
        table_name = table.get("name", "")
        columns = [c.get("name", "") for c in table.get("columns", []) if c.get("name")]
        types = {c.get("name", ""): c.get("type", "") for c in table.get("columns", [])}

        question = _build_question(table_name, columns, types)
        if not question:
            continue

        key = question.lower()
        if key in seen:
            continue
        seen.add(key)

        questions.append(
            {
                "question": question,
                "table": table_name,
                "table_label": humanize(table_name),
                "columns": columns[:6],
            }
        )

        if len(questions) >= limit:
            break

    return questions


def generate_table_summaries(schema: dict) -> list:
    """
    Return a short description of each table, for the schema explorer's
    "Ask about this table" action.
    """
    if not schema or not schema.get("success"):
        return []

    summaries = []
    for table in schema.get("tables", []):
        table_name = table.get("name", "")
        columns = [c.get("name", "") for c in table.get("columns", []) if c.get("name")]
        summaries.append(
            {
                "table": table_name,
                "label": humanize(table_name),
                "summary": f"{len(columns)} column(s): {', '.join(humanize(c) for c in columns[:8])}",
            }
        )
    return summaries
