"""Probe the Cricbuzz API: which endpoints work for YOUR key / plan / version?

Used by ``python -m scripts.check_api`` and by the Data & Settings page. It makes roughly 20 API calls,
so it is only run when you ask for it (free plans have a small monthly quota).
"""

from __future__ import annotations

from typing import Any, Callable

from api.cricbuzz_client import _WORKING  # which candidate route worked
from api.cricbuzz_client import CricbuzzClient  # API access
from services.api_parsers import dig, parse_matches_response  # to pick sample ids
from utils.exceptions import APIAuthError, APIError, APIRateLimitError  # error types


def _attempt(
    client: CricbuzzClient, endpoint: str, label: str, **values: Any
) -> tuple[dict[str, Any], Any]:
    """Run one endpoint; return ``(table row, raw payload or None)``. (``endpoint`` is positional so values may include ``name=``.)"""
    try:
        data = client.call(endpoint, **values)
        keys = list(data)[:4] if isinstance(data, dict) else f"{len(data)} items"
        return {
            "Feature": label,
            "Result": "OK",
            "Details": f"keys: {keys}",
            "Route": f"#{_WORKING.get(endpoint, 0) + 1}",
        }, data
    except APIAuthError as exc:
        return {
            "Feature": label,
            "Result": f"KEY PROBLEM ({exc.status_code})",
            "Details": exc.message,
            "Route": "",
        }, None
    except APIRateLimitError as exc:
        return {
            "Feature": label,
            "Result": "LIMIT REACHED",
            "Details": exc.message,
            "Route": "",
        }, None
    except APIError as exc:
        return {
            "Feature": label,
            "Result": f"FAILED ({exc.status_code or 'network'})",
            "Details": exc.message,
            "Route": "",
        }, None


def probe(
    client: CricbuzzClient, progress: Callable[[float, str], None] | None = None
) -> list[dict[str, Any]]:
    """Test every endpoint the app uses (taking sample ids from the first results)."""
    rows: list[dict[str, Any]] = []
    steps = [
        "recent",
        "live",
        "upcoming",
        "match_info",
        "scorecard",
        "commentary",
        "series_list",
        "series_matches",
        "teams_list",
        "team_players",
        "team_schedule",
        "team_results",
        "venue_info",
        "rankings",
        "top_stats",
        "player_search",
        "player_info",
        "player_batting",
        "player_bowling",
        "news_list",
        "news_detail",
    ]
    done = 0

    def record(row: dict[str, Any]) -> None:
        nonlocal done
        rows.append(row)
        done += 1
        if progress:
            progress(done / len(steps), row["Feature"])

    row, payload = _attempt(client, "recent", "Recent matches")
    record(row)
    sample = (
        next((m for m in parse_matches_response(payload) if m.match_id), None)
        if payload
        else None
    )
    for name, label in (("live", "Live matches"), ("upcoming", "Upcoming matches")):
        record(_attempt(client, name, label)[0])
    for name, label in (
        ("match_info", "Match info"),
        ("scorecard", "Scorecard"),
        ("commentary", "Commentary"),
    ):
        record(
            _attempt(client, name, label, match_id=sample.match_id)[0]
            if sample
            else {
                "Feature": label,
                "Result": "SKIPPED",
                "Details": "no sample match id",
                "Route": "",
            }
        )
    row, series = _attempt(
        client, "series_list", "Series list", category="international"
    )
    record(row)
    series_id = dig(series, "seriesMapProto", 0, "series", 0, "id")
    record(
        _attempt(client, "series_matches", "Series matches", series_id=series_id)[0]
        if series_id
        else {
            "Feature": "Series matches",
            "Result": "SKIPPED",
            "Details": "no sample series id",
            "Route": "",
        }
    )
    row, teams = _attempt(client, "teams_list", "Teams list", category="international")
    record(row)
    team_id = next(
        (
            t.get("teamId")
            for t in dig(teams, "list", default=[])
            if isinstance(t, dict) and t.get("teamId")
        ),
        None,
    )
    for name, label in (
        ("team_players", "Team players"),
        ("team_schedule", "Team schedule"),
        ("team_results", "Team results"),
    ):
        record(
            _attempt(client, name, label, team_id=team_id)[0]
            if team_id
            else {
                "Feature": label,
                "Result": "SKIPPED",
                "Details": "no sample team id",
                "Route": "",
            }
        )
    venue_id = sample.venue_id if sample else None
    record(
        _attempt(client, "venue_info", "Venue info", venue_id=venue_id)[0]
        if venue_id
        else {
            "Feature": "Venue info",
            "Result": "SKIPPED",
            "Details": "no sample venue id",
            "Route": "",
        }
    )
    record(
        _attempt(
            client,
            "rankings",
            "ICC rankings",
            category="batsmen",
            format_type="odi",
            is_women=0,
        )[0]
    )
    record(
        _attempt(
            client,
            "top_stats",
            "Career leaderboards",
            stats_id=0,
            stats_type="mostRuns",
        )[0]
    )
    row, found = _attempt(client, "player_search", "Player search", name="kohli")
    record(row)
    player_id = dig(found, "player", 0, "id")
    for name, label in (
        ("player_info", "Player profile"),
        ("player_batting", "Player batting"),
        ("player_bowling", "Player bowling"),
    ):
        record(
            _attempt(client, name, label, player_id=player_id)[0]
            if player_id
            else {
                "Feature": label,
                "Result": "SKIPPED",
                "Details": "no sample player id",
                "Route": "",
            }
        )
    row, news = _attempt(client, "news_list", "News list")
    record(row)
    news_id = dig(news, "storyList", 0, "story", "id")
    record(
        _attempt(client, "news_detail", "News story", news_id=news_id)[0]
        if news_id
        else {
            "Feature": "News story",
            "Result": "SKIPPED",
            "Details": "no sample story id",
            "Route": "",
        }
    )
    return rows
