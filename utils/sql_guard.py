"""Safety checks for the *Custom SQL* box on the analytics page.

Only a single read-only SELECT / WITH statement is allowed. This is a
defence-in-depth measure - the UI also never exposes write access here.
"""

from __future__ import annotations

import re  # regular expressions

from utils.exceptions import UnsafeQueryError  # raised for rejected queries

MAX_SQL_LENGTH = 10_000  # characters
_FORBIDDEN = re.compile(  # keywords that can change data or the database
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|attach|detach|pragma|grant|revoke|vacuum|merge|call|exec|execute)\b",
    re.IGNORECASE,
)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)  # /* ... */
_LINE_COMMENT = re.compile(r"--[^\n]*")  # -- ...
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")  # 'text' (with '' escapes)


def validate_read_only_sql(sql: str) -> str:
    """Return the cleaned SQL or raise ``UnsafeQueryError``."""
    if not sql or not sql.strip():  # nothing typed
        raise UnsafeQueryError("Please type a SQL query first.")
    if len(sql) > MAX_SQL_LENGTH:  # avoid giant payloads
        raise UnsafeQueryError(f"Query is too long (max {MAX_SQL_LENGTH} characters).")
    cleaned = _BLOCK_COMMENT.sub(" ", sql)  # drop block comments
    cleaned = _LINE_COMMENT.sub(" ", cleaned)  # drop line comments
    cleaned = cleaned.strip().rstrip(";").strip()  # remove trailing semicolons
    if not cleaned:  # only comments were supplied
        raise UnsafeQueryError("Query is empty after removing comments.")
    scan = _STRING_LITERAL.sub("''", cleaned)  # hide text inside quotes before scanning
    if ";" in scan:  # a second statement was attempted
        raise UnsafeQueryError("Only one SQL statement is allowed.")
    if not re.match(
        r"^(select|with)\b", scan, re.IGNORECASE
    ):  # must start with SELECT / WITH
        raise UnsafeQueryError("Only SELECT queries are allowed.")
    match = _FORBIDDEN.search(scan)  # look for dangerous keywords
    if match:
        raise UnsafeQueryError(
            f"The keyword '{match.group(0).upper()}' is not allowed in custom queries."
        )
    return cleaned  # safe to run
