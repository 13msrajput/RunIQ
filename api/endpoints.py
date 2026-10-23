"""Cricbuzz Cricket API (RapidAPI) endpoint paths in ONE place.

Each logical endpoint has a list of CANDIDATE paths. The client tries them in
order and remembers the first one that works, so the app copes with both the
older ``/matches/v1/...`` style routes and the newer ``/matches/...`` style.
Placeholders in braces are filled in by the client; ``Q:`` entries are query
parameters (name -> placeholder).

If RapidAPI changes a route, this is the ONLY file you need to edit. Run
``python -m scripts.check_api`` to see which candidate works for your plan.
"""

from __future__ import annotations

# name -> list of (path template, extra query-parameter templates)
CANDIDATES: dict[str, list[tuple[str, dict[str, str]]]] = {
    # ----- match lists
    "live": [("/matches/v1/live", {}), ("/matches/live", {})],
    "recent": [("/matches/v1/recent", {}), ("/matches/recent", {})],
    "upcoming": [("/matches/v1/upcoming", {}), ("/matches/upcoming", {})],
    # ----- one match
    "match_info": [
        ("/mcenter/v1/{match_id}", {}),
        ("/match-details/get-info", {"matchId": "{match_id}"}),
    ],
    "scorecard": [
        ("/mcenter/v1/{match_id}/hscard", {}),
        ("/mcenter/v1/{match_id}/scard", {}),
        ("/match-details/get-scorecard", {"matchId": "{match_id}"}),
    ],
    "commentary": [
        ("/mcenter/v1/{match_id}/comm", {}),
        ("/match-details/get-commentary", {"matchId": "{match_id}"}),
    ],
    "overs": [
        ("/mcenter/v1/{match_id}/overs", {}),
        ("/match-details/get-overs", {"matchId": "{match_id}"}),
    ],
    # ----- series, teams, venues
    "series_list": [
        ("/series/v1/{category}", {}),
        ("/series/list", {"type": "{category}"}),
    ],
    "series_matches": [
        ("/series/v1/{series_id}", {}),
        ("/series/get-matches", {"seriesId": "{series_id}"}),
    ],
    "teams_list": [
        ("/teams/v1/{category}", {}),
        ("/teams/list", {"type": "{category}"}),
    ],
    "team_players": [
        ("/teams/v1/{team_id}/players", {}),
        ("/teams/get-players", {"teamId": "{team_id}"}),
    ],
    "team_schedule": [
        ("/teams/v1/{team_id}/schedule", {}),
        ("/teams/get-schedules", {"teamId": "{team_id}"}),
    ],
    "team_results": [
        ("/teams/v1/{team_id}/results", {}),
        ("/teams/get-results", {"teamId": "{team_id}"}),
    ],
    "venue_info": [
        ("/venues/v1/{venue_id}", {}),
        ("/venues/get-info", {"venueId": "{venue_id}"}),
    ],
    "venue_matches": [
        ("/venues/v1/{venue_id}/matches", {}),
        ("/venues/get-matches", {"venueId": "{venue_id}"}),
    ],
    # ----- stats and rankings
    "rankings": [
        (
            "/stats/v1/rankings/{category}",
            {"formatType": "{format_type}", "isWomen": "{is_women}"},
        )
    ],
    "top_stats": [("/stats/v1/topstats/{stats_id}", {"statsType": "{stats_type}"})],
    "player_search": [("/stats/v1/player/search", {"plrN": "{name}"})],
    "player_info": [("/stats/v1/player/{player_id}", {})],
    "player_batting": [("/stats/v1/player/{player_id}/batting", {})],
    "player_bowling": [("/stats/v1/player/{player_id}/bowling", {})],
    # ----- news
    "news_list": [("/news/v1/index", {})],
    "news_detail": [("/news/v1/detail/{news_id}", {})],
}
