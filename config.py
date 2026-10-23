"""Central configuration layer for RunIQ.

All secrets and tunables come from environment variables (optionally loaded from
a local ``.env`` file), so no credential is ever hard-coded in the source.
"""

from __future__ import annotations

import os  # read environment variables
from dataclasses import dataclass  # immutable settings container
from functools import lru_cache  # build the settings only once
from pathlib import Path  # OS-independent paths

from dotenv import load_dotenv  # reads the .env file

from utils.exceptions import ConfigurationError  # raised on bad values

BASE_DIR = Path(__file__).resolve().parent  # project root folder
load_dotenv(BASE_DIR / ".env")  # silently ignored when the file does not exist
DEFAULT_SQLITE_PATH = BASE_DIR / "data" / "runiq.db"  # default local database
PLACEHOLDER_KEYS = {
    "",
    "your_rapidapi_key_here",
    "changeme",
}  # values that mean "no key"

# Cricsheet (open ball-by-ball data, ODC-By licence) - URLs verified against cricsheet.org/downloads
CRICSHEET_DOWNLOADS = "https://cricsheet.org/downloads"  # base URL of the zip files
CRICSHEET_PEOPLE_URL = (
    "https://cricsheet.org/register/people.csv"  # player register (ids on other sites)
)
CRICSHEET_ZIPS = (
    {  # format -> zip file (each zip contains BOTH men's and women's matches)
        "Test": "tests_json.zip",
        "ODI": "odis_json.zip",
        "T20I": "t20s_json.zip",
    }
)


def _get_number(name: str, default: float, cast=int):
    """Read a numeric env var, falling back to ``default`` when it is unset."""
    raw = os.getenv(name)  # raw string or None
    if raw is None or raw.strip() == "":  # not provided
        return default  # use the default
    try:
        return cast(raw)  # convert to int / float
    except ValueError as exc:  # user typed something like "ten"
        raise ConfigurationError(
            f"Environment variable {name} must be a number, got '{raw}'."
        ) from exc


@dataclass(frozen=True)
class Settings:
    """Immutable application settings."""

    database_url: str  # SQLAlchemy URL
    rapidapi_key: str  # secret API key
    rapidapi_host: str  # RapidAPI host header value
    api_base_url: str  # https://<host>
    api_timeout: int  # seconds per request
    api_max_retries: int  # automatic retries for 429 / 5xx
    api_backoff_factor: float  # exponential back-off base
    log_level: str  # DEBUG / INFO / WARNING ...
    log_dir: Path  # where log files live
    data_dir: Path  # downloaded Cricsheet zips are cached here

    @property
    def has_api_key(self) -> bool:
        """True when a real (non-placeholder) API key is configured."""
        return self.rapidapi_key.strip().lower() not in PLACEHOLDER_KEYS


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build (once) and return the application settings."""
    host = os.getenv(
        "RAPIDAPI_HOST", "cricbuzz-cricket.p.rapidapi.com"
    ).strip()  # API host
    db_url = (
        os.getenv("DATABASE_URL", "").strip()
        or f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"
    )  # DB URL
    return Settings(
        database_url=db_url,
        rapidapi_key=os.getenv("RAPIDAPI_KEY", "").strip(),
        rapidapi_host=host,
        api_base_url=f"https://{host}",
        api_timeout=_get_number("API_TIMEOUT", 15),
        api_max_retries=_get_number("API_MAX_RETRIES", 2),
        api_backoff_factor=_get_number("API_BACKOFF_FACTOR", 1.0, float),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        log_dir=BASE_DIR / "logs",
        data_dir=BASE_DIR / "data",
    )
