"""
A deterministic stand-in for the model, for testing and demos.

Set `MOCK_LLM=1` and the agent answers from a set of canned responses instead
of calling Gemini. Nothing about the app changes - the same nodes run, the
same safety gate applies, the same response shape comes back - only the model
call is replaced.

This is what makes the interface testable without an API key, and what makes
the test suite deterministic.
"""

import os
import re
import json
from types import SimpleNamespace

MOCK_ENABLED = os.getenv("MOCK_LLM", "").lower() in ("1", "true", "yes", "on")

# Canned answers, keyed by a pattern that matches the user's question.
MOCK_RESPONSES = [
    # Destructive requests come first, so the mock exercises the safety gate
    # rather than falling through to a read.
    (
        r"\b(delete|remove|drop)\b",
        "DELETE FROM Album WHERE AlbumId > 0",
        "That request would remove album records, so it needs your approval before anything is changed.",
    ),
    (
        r"\b(update|change|set)\b",
        "UPDATE Album SET Title = 'Unknown' WHERE AlbumId > 0",
        "That request would change album records, so it needs your approval before anything is changed.",
    ),
    (
        r"\b(insert|add|create)\b",
        "INSERT INTO Playlist (PlaylistId, Name) VALUES (999, 'New Playlist')",
        "That request would add a record, so it needs your approval before anything is changed.",
    ),
    (
        r"\b(how many|count|number of)\b.*\b(album|albums)\b",
        "SELECT COUNT(*) AS album_count FROM Album",
        "There are 347 albums in the database.",
    ),
    (
        r"\b(how many|count|number of)\b.*\b(artist|artists)\b",
        "SELECT COUNT(*) AS artist_count FROM Artist",
        "There are 275 artists in the database.",
    ),
    (
        r"\b(how many|count|number of)\b.*\b(customer|customers)\b",
        "SELECT COUNT(*) AS customer_count FROM Customer",
        "There are 59 customers in the database.",
    ),
    (
        r"\b(how many|count|number of)\b.*\b(track|tracks|song|songs)\b",
        "SELECT COUNT(*) AS track_count FROM Track",
        "There are 3,503 tracks in the database.",
    ),
    (
        r"\b(most|top|best|highest|leading)\b.*\b(artist|artists)\b",
        "SELECT ar.Name AS Artist, COUNT(al.AlbumId) AS AlbumCount\n"
        "FROM Artist ar JOIN Album al ON ar.ArtistId = al.ArtistId\n"
        "GROUP BY ar.Name ORDER BY AlbumCount DESC LIMIT 10",
        "Iron Maiden have the most albums, with 8.",
    ),
    (
        r"\b(most|top|best|highest|longest)\b.*\b(track|tracks|song|songs)\b",
        "SELECT Name, Milliseconds FROM Track ORDER BY Milliseconds DESC LIMIT 10",
        "The longest tracks are around 4,000 milliseconds, or about 4 minutes.",
    ),
    (
        r"\b(revenue|sales|invoice total|total sales)\b",
        "SELECT BillingCountry AS Country, SUM(Total) AS Revenue\n"
        "FROM Invoice GROUP BY BillingCountry ORDER BY Revenue DESC LIMIT 10",
        "The United States leads with the most revenue, followed by France and Brazil.",
    ),
    (
        r"\b(genre|genres)\b",
        "SELECT g.Name AS Genre, COUNT(t.TrackId) AS Tracks\n"
        "FROM Genre g JOIN Track t ON g.GenreId = t.GenreId\n"
        "GROUP BY g.Name ORDER BY Tracks DESC LIMIT 10",
        "Rock is the largest genre, with 1,297 tracks.",
    ),
    (
        r"\b(customer|customers)\b",
        "SELECT c.FirstName || ' ' || c.LastName AS Customer, SUM(i.Total) AS Spent\n"
        "FROM Customer c JOIN Invoice i ON c.CustomerId = i.CustomerId\n"
        "GROUP BY c.FirstName, c.LastName ORDER BY Spent DESC LIMIT 10",
        "The highest-spending customers are from Europe and South America.",
    ),
    (
        r"\b(playlist|playlists)\b",
        "SELECT p.Name AS Playlist, COUNT(pt.TrackId) AS Tracks\n"
        "FROM Playlist p JOIN PlaylistTrack pt ON p.PlaylistId = pt.PlaylistId\n"
        "GROUP BY p.Name ORDER BY Tracks DESC",
        "The Music playlist holds the most tracks, at 3,280.",
    ),
]

FALLBACK_SQL = "SELECT * FROM Album LIMIT 20"
FALLBACK_ANSWER = "Here is a sample of the album table."


def _matches(pattern: str, query: str) -> bool:
    """
    Match a question against a pattern, in either word order.

    "Which artist has the most albums" and "the most albums by artist" mean
    the same question, so a pattern like "most ... artist" has to match both.
    The keyword groups are pulled straight out of the pattern's parentheses,
    and a match needs every alternative of every group to appear somewhere in
    the question - so "top genre by tracks" does not match "most ... track".
    """
    if re.search(pattern, query, re.IGNORECASE):
        return True

    groups = re.findall(r"\(([^)]*)\)", pattern)
    if len(groups) < 2:
        return False

    for group in groups:
        options = [o.strip() for o in group.split("|") if o.strip()]
        if not options:
            continue
        # The alternatives in a group are synonyms, so ONE of them matching
        # is enough - "most" and "top" are the same idea.
        if not any(
            re.search(rf"\b{re.escape(o)}\w*\b", query, re.IGNORECASE)
            for o in options
        ):
            return False

    return True


def mock_sql(query: str) -> str:
    """The SQL a mock answer would use for this question."""
    for pattern, sql, _ in MOCK_RESPONSES:
        if _matches(pattern, query):
            return sql
    return FALLBACK_SQL


def mock_answer(query: str) -> str:
    """The prose a mock answer would give for this question."""
    for pattern, _, answer in MOCK_RESPONSES:
        if _matches(pattern, query):
            return answer
    return FALLBACK_ANSWER


def mock_summary(sql: str, columns: list, rows: list) -> tuple:
    """
    The insight / explanation / follow-ups a mock answer would produce,
    in the same labelled format the real prompt asks for.
    """
    row_count = len(rows)
    insight = f"The result contains {row_count} row(s)."
    if rows:
        first = rows[0]
        key = list(first.keys())[0]
        insight += f" The first row shows {key} of {first[key]}."

    explanation = "This query reads the requested data and returns it as a table."

    follow_ups = [
        "Show me the top 5 by this measure",
        "What is the average across the whole table?",
        "Break this down by month",
    ]

    return insight, explanation, follow_ups


def mock_steps(sql: str, tables: list) -> list:
    """The step breakdown a mock answer would produce."""
    table = tables[0] if tables else "the table"
    return [
        f"Start from the {table} table",
        "Count the rows that match",
        "Return the count",
    ]


def format_mock_summary(user_prompt: str) -> str:
    """Render the mock's insight, explanation and follow-ups in the format
    the real prompt asks the model for."""
    rows = []
    match = re.search(r"Data \(first 50 rows\):\n(\[.*?\])\n", user_prompt, re.DOTALL)
    if match:
        try:
            rows = json.loads(match.group(1))
        except Exception:
            rows = []

    insight, explanation, follow_ups = mock_summary("", [], rows)
    return (
        f"INSIGHT: {insight}\n"
        f"EXPLANATION: {explanation}\n"
        f"FOLLOW_UPS: {' | '.join(follow_ups)}"
    )


def mock_completion(messages):
    """
    A stand-in for litellm's response object.

    The agent asks for three different things - SQL, prose, and a labelled
    summary - so the mock inspects the system prompt to work out which one
    is being asked for.
    """
    system = ""
    user = ""
    for message in messages:
        if message.get("role") == "system":
            system += message.get("content", "")
        else:
            user += message.get("content", "")

    if "Return ONLY the raw SQL query string" in system:
        content = mock_sql(user)
    elif "Reply in this exact format" in system:
        content = format_mock_summary(user)
    elif "synthesize the raw database results" in system:
        content = mock_answer(user)
    else:
        content = mock_answer(user)

    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
