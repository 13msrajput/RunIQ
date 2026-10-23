"""Centralized database access for RunIQ (engine, transactions, helpers).

Every other module talks to the database ONLY through this file, so switching
from SQLite to PostgreSQL / MySQL means changing ``DATABASE_URL`` and nothing
else.
"""

from __future__ import annotations

import math  # square root for the SQLite STDDEV aggregate
import threading  # protects the lazily created engine
from contextlib import contextmanager  # "with get_connection() as conn"
from pathlib import Path  # create the SQLite folder
from typing import Any, Iterator

import pandas as pd  # query results as DataFrames
from sqlalchemy import create_engine, event, text  # SQLAlchemy core API
from sqlalchemy.engine import Connection, Engine  # type hints
from sqlalchemy.engine.url import make_url  # parse DATABASE_URL
from sqlalchemy.exc import IntegrityError, SQLAlchemyError  # DB error classes

from config import get_settings  # DATABASE_URL lives here
from models.schema import metadata  # table definitions
from models.views import VIEW_DEFINITIONS  # view definitions
from utils.exceptions import ConfigurationError, DatabaseError  # our errors
from utils.logger import get_logger  # logging

logger = get_logger("db")  # module logger
_engine: Engine | None = None  # singleton engine
_engine_lock = threading.Lock()  # thread-safety for the singleton


class _SampleStdDev:
    """SQLite aggregate: SAMPLE standard deviation (same meaning as STDDEV in PostgreSQL)."""

    def __init__(self) -> None:
        self.count = 0  # values seen
        self.mean = 0.0  # running mean (Welford's algorithm)
        self.m2 = 0.0  # running sum of squared differences

    def step(self, value: Any) -> None:
        """Called once per row."""
        if value is None:  # SQL aggregates ignore NULL
            return
        self.count += 1  # one more value
        delta = float(value) - self.mean  # distance from old mean
        self.mean += delta / self.count  # update mean
        self.m2 += delta * (float(value) - self.mean)  # update squared distance

    def finalize(self) -> float | None:
        """Called once at the end of the group."""
        if self.count < 2:  # standard deviation needs two values
            return None
        return math.sqrt(self.m2 / (self.count - 1))  # sample std-dev


def _build_engine(url: str) -> Engine:
    """Create an engine for ``url`` with sensible defaults per database."""
    try:
        parsed = make_url(url)  # validates the URL format
        connect_args: dict[str, Any] = {}  # driver specific options
        if parsed.get_backend_name() == "sqlite":
            if parsed.database and parsed.database != ":memory:":
                Path(parsed.database).parent.mkdir(
                    parents=True, exist_ok=True
                )  # create data/ folder
            connect_args["check_same_thread"] = False  # Streamlit uses several threads
        engine = create_engine(
            url, pool_pre_ping=True, connect_args=connect_args
        )  # lazy connect
    except (
        SQLAlchemyError,
        ImportError,
        ValueError,
    ) as exc:  # bad URL or missing driver
        raise ConfigurationError(
            "Invalid DATABASE_URL or missing database driver.", details=str(exc)
        ) from exc
    if engine.dialect.name == "sqlite":  # SQLite needs two extras

        @event.listens_for(engine, "connect")
        def _on_connect(
            dbapi_connection, _record
        ) -> None:  # runs for every new connection
            cursor = dbapi_connection.cursor()  # plain DB-API cursor
            cursor.execute(
                "PRAGMA foreign_keys=ON"
            )  # enforce FKs (off by default in SQLite)
            cursor.close()  # tidy up
            dbapi_connection.create_aggregate(
                "STDDEV", 1, _SampleStdDev
            )  # SQL STDDEV() for analytics

    return engine  # ready to use


def get_engine() -> Engine:
    """Return the shared engine, creating it on first use."""
    global _engine  # we assign to the module level variable
    if _engine is None:  # fast path: already built
        with _engine_lock:  # only one thread may build it
            if _engine is None:  # double-checked locking
                _engine = _build_engine(get_settings().database_url)
                logger.info("Database engine created (%s)", _engine.dialect.name)
    return _engine


def set_database_url(url: str) -> Engine:
    """Replace the engine (used by tests and scripts)."""
    global _engine  # module level variable
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()  # close old pool
        _engine = _build_engine(url)  # build new one
    return _engine


def _translate(exc: SQLAlchemyError, action: str) -> DatabaseError:
    """Wrap a raw SQLAlchemy error in our own ``DatabaseError``."""
    logger.error(
        "Database error during %s: %s", action, exc
    )  # keep technical detail in the log
    return DatabaseError(
        f"Database operation failed while {action}.", original=exc, details=str(exc)
    )


@contextmanager
def get_connection(action: str = "running a query") -> Iterator[Connection]:
    """Yield a transactional connection (commit on success, rollback on error)."""
    engine = get_engine()  # shared engine
    try:
        with engine.begin() as conn:  # begin() = automatic commit / rollback
            yield conn  # caller works here
    except SQLAlchemyError as exc:  # any database failure
        raise _translate(exc, action) from exc


def is_integrity_error(exc: DatabaseError) -> bool:
    """True when a ``DatabaseError`` was caused by a constraint violation."""
    return isinstance(exc.original, IntegrityError)


def run_query(sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """Execute a SELECT and return a DataFrame."""
    with get_connection("reading data") as conn:  # open connection
        return pd.read_sql_query(text(sql), conn, params=params or {})  # run + convert


def execute_script_statements(statements: list[str]) -> None:
    """Run several DDL statements in one transaction."""
    with get_connection("running a script") as conn:
        for statement in statements:  # one by one
            conn.execute(text(statement))


def create_schema() -> None:
    """Create all tables, indexes and views (safe to call repeatedly)."""
    engine = get_engine()
    try:
        metadata.create_all(engine)  # CREATE TABLE IF NOT EXISTS + indexes
    except SQLAlchemyError as exc:
        raise _translate(exc, "creating the schema") from exc
    with get_connection("creating views") as conn:
        for name, ddl in VIEW_DEFINITIONS:  # recreate views so they stay current
            conn.execute(text(f"DROP VIEW IF EXISTS {name}"))
            conn.execute(text(ddl))
    logger.info("Schema ready")


def reset_database() -> None:
    """DROP everything and recreate an empty schema (destructive!)."""
    engine = get_engine()
    with get_connection("dropping views") as conn:
        for name, _ in VIEW_DEFINITIONS:
            conn.execute(text(f"DROP VIEW IF EXISTS {name}"))
    try:
        metadata.drop_all(engine)  # drop tables in dependency order
    except SQLAlchemyError as exc:
        raise _translate(exc, "dropping tables") from exc
    create_schema()  # rebuild


def check_connection() -> tuple[bool, str]:
    """Return ``(ok, message)`` - never raises (used by the status panel)."""
    try:
        with get_connection("checking the connection") as conn:
            conn.execute(text("SELECT 1"))  # cheapest possible query
        return True, f"Connected ({get_engine().dialect.name})"
    except (DatabaseError, ConfigurationError) as exc:
        return False, exc.message


def table_counts() -> dict[str, int]:
    """Row counts for the main tables; empty dict if the schema is missing."""
    counts: dict[str, int] = {}  # result
    try:
        with get_connection("counting rows") as conn:
            for name in (
                "teams",
                "venues",
                "players",
                "series",
                "matches",
                "innings",
                "batting_performances",
                "bowling_performances",
                "player_career_stats",
            ):
                counts[name] = int(
                    conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar() or 0
                )
    except (DatabaseError, ConfigurationError):  # tables not created yet
        return {}
    return counts


def run_scalar(sql: str, params: dict[str, Any] | None = None) -> Any:
    """Execute a query and return the first column of the first row (or ``None``)."""
    with get_connection("reading a value") as conn:
        return conn.execute(text(sql), params or {}).scalar()


def execute_many(sql: str, rows: list[dict[str, Any]]) -> None:
    """Run one parameterised statement for many rows inside ONE transaction."""
    if not rows:
        return
    with get_connection("bulk update") as conn:
        conn.execute(text(sql), rows)
