"""Unit tests for validators and the SQL guard."""

from datetime import date, timedelta

import pytest

from utils.exceptions import UnsafeQueryError, ValidationError
from utils.sql_guard import validate_read_only_sql
from utils.validators import require_text, validate_choice, validate_date, validate_int


def test_require_text_strips_and_checks_length():
    assert require_text("  Virat  ", "Name") == "Virat"
    with pytest.raises(ValidationError):
        require_text("a", "Name")
    with pytest.raises(ValidationError):
        require_text(None, "Name")


@pytest.mark.parametrize("value,ok", [("12", 12), (12.0, 12)])
def test_validate_int_accepts_whole_numbers(value, ok):
    assert validate_int(value, "N") == ok


@pytest.mark.parametrize("value", ["abc", 1.5, True])
def test_validate_int_rejects_bad_values(value):
    with pytest.raises(ValidationError):
        validate_int(value, "N")


def test_validate_choice_and_date():
    assert validate_choice("ODI", "F", ("Test", "ODI")) == "ODI"
    with pytest.raises(ValidationError):
        validate_choice("T10", "F", ("Test", "ODI"))
    with pytest.raises(ValidationError):
        validate_date(date.today() + timedelta(days=2), "D", not_in_future=True)
    assert validate_date("2024-02-03", "D") == date(2024, 2, 3)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE players",
        "SELECT 1; DELETE FROM players",
        "UPDATE players SET full_name='x'",
        "PRAGMA table_info(players)",
        "",
        "-- only a comment",
    ],
)
def test_guard_blocks_dangerous_sql(sql):
    with pytest.raises(UnsafeQueryError):
        validate_read_only_sql(sql)


def test_guard_allows_select_and_cte_and_ignores_keywords_in_strings():
    assert validate_read_only_sql("SELECT 'drop table' AS x;").startswith("SELECT")
    assert validate_read_only_sql("WITH a AS (SELECT 1) SELECT * FROM a").startswith(
        "WITH"
    )
