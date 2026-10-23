"""Small, reusable input validators.

Every function either returns a *clean* value or raises ``ValidationError``
with a message that is safe to show to the end user.
"""

from __future__ import annotations

from datetime import date, datetime  # date handling
from typing import Any, Iterable  # type hints

from utils.exceptions import ValidationError  # our error type


def require_text(
    value: Any, field: str, *, min_length: int = 2, max_length: int = 120
) -> str:
    """Return stripped text or raise when missing / too short / too long."""
    if value is None:  # nothing supplied
        raise ValidationError(f"{field} is required.")
    text = str(value).strip()  # remove surrounding spaces
    if len(text) < min_length:  # too short (or empty)
        raise ValidationError(f"{field} must be at least {min_length} characters long.")
    if len(text) > max_length:  # too long for the column
        raise ValidationError(f"{field} must be at most {max_length} characters long.")
    return text  # valid


def optional_text(value: Any, field: str, *, max_length: int = 120) -> str | None:
    """Like ``require_text`` but returns ``None`` for empty input."""
    if value is None or str(value).strip() == "":  # blank means "not provided"
        return None
    return require_text(value, field, min_length=1, max_length=max_length)


def validate_choice(
    value: Any, field: str, allowed: Iterable[str], *, required: bool = True
) -> str | None:
    """Ensure ``value`` is one of ``allowed``."""
    allowed = tuple(allowed)  # freeze for the message
    if value is None or str(value).strip() == "":  # blank
        if required:
            raise ValidationError(f"{field} is required.")
        return None
    text = str(value).strip()  # normalise
    if text not in allowed:  # not an allowed option
        raise ValidationError(f"{field} must be one of: {', '.join(allowed)}.")
    return text


def validate_int(
    value: Any,
    field: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    required: bool = True,
) -> int | None:
    """Convert to ``int`` and enforce optional bounds."""
    if value is None or (isinstance(value, str) and value.strip() == ""):  # blank
        if required:
            raise ValidationError(f"{field} is required.")
        return None
    if isinstance(value, bool):  # True/False are ints in Python - reject them
        raise ValidationError(f"{field} must be a whole number.")
    try:
        number = float(value)  # accept "12", 12, 12.0
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be a whole number.") from exc
    if number != int(number):  # reject 12.5
        raise ValidationError(f"{field} must be a whole number.")
    result = int(number)  # final integer
    if minimum is not None and result < minimum:  # lower bound
        raise ValidationError(f"{field} must be at least {minimum}.")
    if maximum is not None and result > maximum:  # upper bound
        raise ValidationError(f"{field} must be at most {maximum}.")
    return result


def validate_float(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    required: bool = True,
) -> float | None:
    """Convert to ``float`` and enforce optional bounds."""
    if value is None or (isinstance(value, str) and value.strip() == ""):  # blank
        if required:
            raise ValidationError(f"{field} is required.")
        return None
    try:
        number = float(value)  # may raise
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be a number.") from exc
    if number != number:  # NaN check (NaN != NaN)
        raise ValidationError(f"{field} must be a valid number.")
    if minimum is not None and number < minimum:  # lower bound
        raise ValidationError(f"{field} must be at least {minimum}.")
    if maximum is not None and number > maximum:  # upper bound
        raise ValidationError(f"{field} must be at most {maximum}.")
    return round(number, 2)  # two decimals match the Numeric(10, 2) columns


def validate_date(
    value: Any,
    field: str,
    *,
    required: bool = True,
    not_in_future: bool = False,
    minimum: date = date(1900, 1, 1),
) -> date | None:
    """Accept ``date``, ``datetime`` or ISO string (YYYY-MM-DD)."""
    if value is None or (isinstance(value, str) and value.strip() == ""):  # blank
        if required:
            raise ValidationError(f"{field} is required.")
        return None
    if isinstance(value, datetime):  # datetime -> date
        parsed = value.date()
    elif isinstance(value, date):  # already a date
        parsed = value
    else:
        try:
            parsed = datetime.strptime(
                str(value).strip(), "%Y-%m-%d"
            ).date()  # ISO string
        except ValueError as exc:
            raise ValidationError(
                f"{field} must be a valid date in YYYY-MM-DD format."
            ) from exc
    if parsed < minimum:  # unrealistically old
        raise ValidationError(f"{field} cannot be before {minimum.isoformat()}.")
    if not_in_future and parsed > date.today():  # future dates not allowed
        raise ValidationError(f"{field} cannot be in the future.")
    return parsed


def validate_bool(value: Any, field: str) -> bool:
    """Strictly accept real booleans (checkbox values)."""
    if isinstance(value, bool):  # ok
        return value
    raise ValidationError(f"{field} must be True or False.")
