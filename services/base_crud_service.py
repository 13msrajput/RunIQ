"""Generic, validated CRUD engine shared by every entity service (DRY + OOP).

A subclass only declares: the table, the primary-key column(s) and one
validation rule per editable column. Create / Read / Update / Delete,
transactions and friendly error translation are inherited.
"""

from __future__ import annotations

from typing import Any, Callable  # type hints

import pandas as pd  # tabular reads
from sqlalchemy import Table, delete, insert, select, update  # Core statements

from utils.db_connection import get_connection, is_integrity_error  # DB helpers
from utils.exceptions import (
    DatabaseError,
    RecordNotFoundError,
    ValidationError,
)  # errors
from utils.logger import get_logger  # logging

logger = get_logger("crud")  # module logger


class BaseCrudService:
    """Base class: subclasses set ``table``, ``pk_columns``, ``rules`` and ``required_on_create``."""

    entity_name = "record"  # used in messages
    table: Table  # SQLAlchemy table
    pk_columns: tuple[str, ...] = ()  # primary key column names (may be composite)
    rules: dict[str, Callable[[Any], Any]] = (
        {}
    )  # column -> validator returning the clean value
    required_on_create: tuple[str, ...] = ()  # columns that must be supplied

    # ----------------------------------------------------------- hooks
    def cross_validate(self, merged: dict[str, Any]) -> None:
        """Override for rules that involve several columns."""

    def derived_fields(self, merged: dict[str, Any]) -> dict[str, Any]:
        """Override to compute columns automatically (e.g. match_year)."""
        return {}

    # ------------------------------------------------------ validation
    def _clean(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate each supplied column with its rule."""
        clean: dict[str, Any] = {}
        for column, value in data.items():
            if (
                column not in self.rules
            ):  # protects against unexpected / forbidden columns
                raise ValidationError(
                    f"'{column}' cannot be set on a {self.entity_name}."
                )
            clean[column] = self.rules[column](value)  # may raise ValidationError
        return clean

    def _pk_filter(self, pk: dict[str, Any]):
        """Build a WHERE clause from a primary-key dict."""
        missing = [c for c in self.pk_columns if c not in pk or pk[c] in (None, "")]
        if missing:
            raise ValidationError(f"Missing key value(s): {', '.join(missing)}.")
        clause = None
        for column in self.pk_columns:
            condition = self.table.c[column] == pk[column]  # column = value
            clause = (
                condition if clause is None else clause & condition
            )  # AND them together
        return clause

    def _translate(self, exc: DatabaseError) -> Exception:
        """Turn constraint violations into friendly validation messages."""
        if is_integrity_error(exc):
            text = str(exc.original).lower()
            if "unique" in text or "duplicate" in text:
                return ValidationError(
                    f"This {self.entity_name} already exists (duplicate value)."
                )
            if "foreign key" in text:
                return ValidationError(
                    f"The {self.entity_name} refers to a record that does not exist, or is still used by other data."
                )
            return ValidationError(
                f"The values break a data rule for {self.entity_name}.",
                details=str(exc.original),
            )
        return exc

    # ------------------------------------------------------------ CRUD
    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """INSERT one row and return its primary key."""
        missing = [c for c in self.required_on_create if data.get(c) in (None, "")]
        if missing:
            raise ValidationError(f"Required: {', '.join(missing)}.")
        clean = self._clean(data)  # validate columns
        self.cross_validate(clean)  # multi-column rules
        clean.update(self.derived_fields(clean))  # computed columns
        try:
            with get_connection(
                f"creating a {self.entity_name}"
            ) as conn:  # one transaction
                result = conn.execute(insert(self.table).values(**clean))
                pk = dict(
                    zip(
                        (c.name for c in self.table.primary_key.columns),
                        result.inserted_primary_key,
                    )
                )
        except DatabaseError as exc:
            raise self._translate(exc) from exc
        logger.info("Created %s %s", self.entity_name, pk)
        return pk

    def get(self, pk: dict[str, Any]) -> dict[str, Any] | None:
        """SELECT one row by primary key (``None`` when missing)."""
        with get_connection(f"reading a {self.entity_name}") as conn:
            row = (
                conn.execute(select(self.table).where(self._pk_filter(pk)))
                .mappings()
                .first()
            )
        return dict(row) if row else None

    def read_all(self, limit: int = 500) -> pd.DataFrame:
        """SELECT rows (newest key first) as a DataFrame."""
        order = [self.table.c[c].desc() for c in self.pk_columns]
        with get_connection(f"listing {self.entity_name}s") as conn:
            rows = (
                conn.execute(select(self.table).order_by(*order).limit(int(limit)))
                .mappings()
                .all()
            )
        return pd.DataFrame([dict(r) for r in rows])

    def update(self, pk: dict[str, Any], changes: dict[str, Any]) -> None:
        """UPDATE the given columns of one row."""
        if not changes:
            raise ValidationError("Nothing to update - change at least one field.")
        existing = self.get(pk)  # raises on bad pk
        if existing is None:
            raise RecordNotFoundError(f"{self.entity_name.capitalize()} not found.")
        clean = self._clean(changes)  # validate only the changed columns
        merged = {**existing, **clean}  # what the row will look like afterwards
        self.cross_validate(merged)  # multi-column rules on the final state
        clean.update(self.derived_fields(merged))  # keep derived columns in sync
        try:
            with get_connection(f"updating a {self.entity_name}") as conn:
                result = conn.execute(
                    update(self.table).where(self._pk_filter(pk)).values(**clean)
                )
                if result.rowcount == 0:  # deleted by someone else meanwhile
                    raise RecordNotFoundError(
                        f"{self.entity_name.capitalize()} not found."
                    )
        except DatabaseError as exc:
            raise self._translate(exc) from exc
        logger.info("Updated %s %s", self.entity_name, pk)

    def delete(self, pk: dict[str, Any]) -> None:
        """DELETE one row."""
        try:
            with get_connection(f"deleting a {self.entity_name}") as conn:
                result = conn.execute(delete(self.table).where(self._pk_filter(pk)))
                if result.rowcount == 0:
                    raise RecordNotFoundError(
                        f"{self.entity_name.capitalize()} not found."
                    )
        except DatabaseError as exc:
            raise self._translate(exc) from exc
        logger.info("Deleted %s %s", self.entity_name, pk)
