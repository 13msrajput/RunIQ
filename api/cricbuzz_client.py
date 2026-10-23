"""Defensive HTTP client for the Cricbuzz Cricket API on RapidAPI.

Responsibilities
* add the authentication headers
* try each candidate route (see ``api/endpoints.py``) until one works
* retry temporary failures (429 / 5xx) with exponential back-off
* turn every failure mode into one of OUR exceptions (never a raw traceback)
"""

from __future__ import annotations

import threading  # protects the route memory
from typing import Any  # type hints

import requests  # HTTP library
from requests.adapters import HTTPAdapter  # lets us mount retry logic
from urllib3.util.retry import Retry  # automatic retries with back-off

from api.endpoints import CANDIDATES  # route candidates
from config import Settings, get_settings  # credentials + tunables
from utils.exceptions import APIAuthError, APIError, APIRateLimitError  # our errors
from utils.logger import get_logger  # logging

logger = get_logger("api")  # module logger
_WORKING: dict[str, int] = (
    {}
)  # endpoint name -> index of the candidate that worked (shared by all clients)
_LOCK = threading.Lock()  # guards _WORKING


class CricbuzzClient:
    """Wrapper around the REST API. One instance can be reused for many calls."""

    def __init__(
        self, settings: Settings | None = None, session: requests.Session | None = None
    ) -> None:
        self.settings = settings or get_settings()  # configuration
        self.session = (
            session or self._build_session()
        )  # HTTP session (injectable for tests)

    # ----------------------------------------------------------------- setup
    def _build_session(self) -> requests.Session:
        """Create a Session that retries temporary failures automatically."""
        retry = Retry(
            total=self.settings.api_max_retries,
            backoff_factor=self.settings.api_backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        session = requests.Session()  # connection pooling
        session.mount("https://", HTTPAdapter(max_retries=retry))
        return session

    def _headers(self) -> dict[str, str]:
        """RapidAPI authentication headers."""
        return {
            "X-RapidAPI-Key": self.settings.rapidapi_key,
            "X-RapidAPI-Host": self.settings.rapidapi_host,
        }

    # --------------------------------------------------------------- request
    def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET ``path`` and return parsed JSON, raising our exceptions on failure."""
        if not self.settings.has_api_key:  # fail fast with a helpful message
            raise APIAuthError(
                "RAPIDAPI_KEY is not configured. Add it to your .env file.",
                status_code=401,
            )
        url = f"{self.settings.api_base_url}{path}"
        try:
            response = self.session.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=self.settings.api_timeout,
            )
        except requests.exceptions.Timeout as exc:
            logger.warning("Timeout calling %s", path)
            raise APIError(
                "The Cricbuzz API timed out. Please try again.", details=str(exc)
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            logger.warning("Connection error calling %s", path)
            raise APIError(
                "Could not connect to the Cricbuzz API. Check your internet connection.",
                details=str(exc),
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise APIError(
                "Unexpected error while calling the Cricbuzz API.", details=str(exc)
            ) from exc
        remaining = response.headers.get(
            "x-ratelimit-requests-remaining"
        )  # RapidAPI quota header
        if remaining is not None:
            logger.info("API quota remaining: %s", remaining)
        status = response.status_code
        if status in (401, 403):
            raise APIAuthError(
                "The API key was rejected. Check RAPIDAPI_KEY and that you subscribed to the API on RapidAPI.",
                status_code=status,
            )
        if status == 429:
            raise APIRateLimitError(
                "API rate limit or monthly quota exceeded. Wait a while and try again.",
                status_code=status,
            )
        if status == 404:
            raise APIError(
                "The requested data was not found on Cricbuzz.", status_code=status
            )
        if status >= 400:
            raise APIError(
                f"Cricbuzz API returned HTTP {status}.",
                status_code=status,
                details=response.text[:300],
            )
        try:
            return response.json()
        except ValueError as exc:
            raise APIError(
                "The Cricbuzz API returned invalid JSON.",
                status_code=status,
                details=response.text[:300],
            ) from exc

    def call(self, endpoint: str, /, **values: Any) -> Any:
        """Call the logical endpoint ``endpoint`` with placeholder ``values`` (tries candidates in order).

        ``endpoint`` is positional-only so a placeholder may itself be called ``name`` (player search).
        """
        candidates = CANDIDATES.get(endpoint)
        if not candidates:
            raise APIError(f"Unknown endpoint '{endpoint}'.")
        with _LOCK:
            start = _WORKING.get(
                endpoint, 0
            )  # begin with the candidate that worked last time
        order = [start] + [i for i in range(len(candidates)) if i != start]
        last_404: APIError | None = None
        for index in order:
            template, extra = candidates[index]
            try:
                path = template.format(**values)
                params = {
                    key: str(value).format(**values) for key, value in extra.items()
                }
            except KeyError as exc:  # a placeholder is missing for this candidate
                raise APIError(
                    f"Missing value {exc} for endpoint '{endpoint}'."
                ) from exc
            try:
                data = self._request(path, params or None)
            except APIError as exc:
                if (
                    exc.status_code == 404 and index != order[-1]
                ):  # try the next candidate route
                    last_404 = exc
                    continue
                raise
            with _LOCK:
                _WORKING[endpoint] = index  # remember the working route
            return data
        raise last_404 or APIError(f"No working route found for '{endpoint}'.")

    # ------------------------------------------------------- named helpers
    def get_live_matches(self) -> Any:
        return self.call("live")

    def get_recent_matches(self) -> Any:
        return self.call("recent")

    def get_upcoming_matches(self) -> Any:
        return self.call("upcoming")

    def get_match_info(self, match_id: int) -> Any:
        return self.call("match_info", match_id=int(match_id))

    def get_scorecard(self, match_id: int) -> Any:
        return self.call("scorecard", match_id=int(match_id))

    def get_commentary(self, match_id: int) -> Any:
        return self.call("commentary", match_id=int(match_id))

    def get_overs(self, match_id: int) -> Any:
        return self.call("overs", match_id=int(match_id))

    def get_series_list(self, category: str = "international") -> Any:
        return self.call("series_list", category=category)

    def get_series_matches(self, series_id: int) -> Any:
        return self.call("series_matches", series_id=int(series_id))

    def get_teams(self, category: str = "international") -> Any:
        return self.call("teams_list", category=category)

    def get_team_players(self, team_id: int) -> Any:
        return self.call("team_players", team_id=int(team_id))

    def get_team_schedule(self, team_id: int) -> Any:
        return self.call("team_schedule", team_id=int(team_id))

    def get_team_results(self, team_id: int) -> Any:
        return self.call("team_results", team_id=int(team_id))

    def get_venue(self, venue_id: int) -> Any:
        return self.call("venue_info", venue_id=int(venue_id))

    def get_rankings(
        self,
        category: str = "batsmen",
        format_type: str = "test",
        is_women: bool = False,
    ) -> Any:
        return self.call(
            "rankings",
            category=category,
            format_type=format_type,
            is_women=1 if is_women else 0,
        )

    def get_top_stats(self, stats_type: str = "mostRuns", stats_id: int = 0) -> Any:
        return self.call("top_stats", stats_id=stats_id, stats_type=stats_type)

    def search_player(self, name: str) -> Any:
        return self.call("player_search", name=name)

    def get_player_info(self, player_id: int) -> Any:
        return self.call("player_info", player_id=int(player_id))

    def get_player_batting(self, player_id: int) -> Any:
        return self.call("player_batting", player_id=int(player_id))

    def get_player_bowling(self, player_id: int) -> Any:
        return self.call("player_bowling", player_id=int(player_id))

    def get_news(self) -> Any:
        return self.call("news_list")

    def get_news_detail(self, news_id: int) -> Any:
        return self.call("news_detail", news_id=int(news_id))
