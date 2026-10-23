"""Runs the prepared SQL questions and the guarded custom SQL box."""

from __future__ import annotations

import time  # measure execution time
from dataclasses import dataclass

import pandas as pd  # tables

from sql.queries import QUERIES, QUERY_INDEX, AnalyticsQuery  # query catalogue
from utils.db_connection import run_query  # SQL -> DataFrame
from utils.exceptions import ValidationError  # unknown query id
from utils.logger import get_logger  # logging
from utils.sql_guard import validate_read_only_sql  # safety check

logger = get_logger("analytics")  # module logger
CUSTOM_ROW_LIMIT = 1000  # protects the browser from huge results


@dataclass
class QueryResult:
    """DataFrame + metadata for display."""

    data: pd.DataFrame
    seconds: float


class AnalyticsService:
    """Facade over the query catalogue."""

    def list_queries(self, level: str | None = None) -> list[AnalyticsQuery]:
        """All queries, optionally limited to one level."""
        return [q for q in QUERIES if level in (None, "All") or q.level == level]

    def run(self, number: str) -> QueryResult:
        """Execute one prepared query."""
        query = QUERY_INDEX.get(str(number).upper())
        if query is None:
            raise ValidationError(f"Unknown query number: {number}")
        started = time.perf_counter()
        data = run_query(
            query.sql, query.params()
        )  # DatabaseError propagates to the UI
        seconds = time.perf_counter() - started
        logger.info("Query %s -> %d rows in %.3fs", number, len(data), seconds)
        return QueryResult(data, seconds)

    def run_custom(self, sql: str) -> QueryResult:
        """Execute user-typed SQL after validating it is a read-only SELECT."""
        safe_sql = validate_read_only_sql(sql)  # raises UnsafeQueryError
        wrapped = f"SELECT * FROM ({safe_sql}) AS custom_query LIMIT {CUSTOM_ROW_LIMIT}"  # cap the rows
        started = time.perf_counter()
        data = run_query(wrapped)
        return QueryResult(data, time.perf_counter() - started)
