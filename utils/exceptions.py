"""Custom exception hierarchy used across RunIQ.

Using our own exception types lets the UI layer catch *specific* problems
(API down, bad input, DB failure) and show a friendly message instead of a
raw traceback.
"""

from __future__ import annotations  # allows modern type hints on older Python versions


class CricbuzzError(Exception):
    """Base class for every error raised intentionally by this project."""

    def __init__(self, message: str, *, details: str | None = None) -> None:
        super().__init__(message)  # keep the normal Exception behaviour
        self.message = message  # short, user-friendly text
        self.details = details  # optional technical detail for logs / expanders


class ConfigurationError(CricbuzzError):
    """Raised when settings (env vars, DB URL, drivers) are missing or invalid."""


class APIError(CricbuzzError):
    """Raised when the Cricbuzz API call fails (network, HTTP, bad JSON)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        details: str | None = None,
    ) -> None:
        super().__init__(message, details=details)  # reuse base initializer
        self.status_code = status_code  # HTTP status if we got one


class APIAuthError(APIError):
    """Raised for missing / invalid API key (HTTP 401 or 403)."""


class APIRateLimitError(APIError):
    """Raised when the RapidAPI quota or rate limit is exceeded (HTTP 429)."""


class DatabaseError(CricbuzzError):
    """Raised when a database operation fails."""

    def __init__(
        self,
        message: str,
        *,
        original: Exception | None = None,
        details: str | None = None,
    ) -> None:
        super().__init__(message, details=details)  # base initializer
        self.original = original  # the underlying SQLAlchemy / driver exception


class ValidationError(CricbuzzError):
    """Raised when user input breaks a business rule (bad value, duplicate...)."""


class RecordNotFoundError(CricbuzzError):
    """Raised when an update / delete / read targets a row that does not exist."""


class UnsafeQueryError(ValidationError):
    """Raised when a custom SQL query is not a safe, read-only SELECT."""


class DataImportError(CricbuzzError):
    """Raised when downloading or importing the Cricsheet match data fails."""
