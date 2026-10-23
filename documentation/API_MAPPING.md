# Cricbuzz API analysis and mapping

* **Base URL:** `https://cricbuzz-cricket.p.rapidapi.com` (host from `.env`) · **Method:** GET only
* **Headers:** `X-RapidAPI-Key`, `X-RapidAPI-Host` · **Limits:** set by your plan (HTTP 429 when exceeded; the `x-ratelimit-requests-remaining` header is logged)
* **Responses:** JSON. Match lists are nested: `typeMatches -> seriesMatches -> seriesAdWrapper -> matches -> matchInfo / matchScore`.
* **Routes:** every logical endpoint has candidate routes in `api/endpoints.py` (older `/matches/v1/live` style first, newer `/matches/live` style second). The client uses the first that does not return 404 and remembers it.

| Logical endpoint | Used by | Stored in |
|---|---|---|
| live / recent / upcoming | Home, Matches, *Save to database* | `matches`, `teams`, `venues`, `series` |
| match_info, scorecard, commentary | Match Centre | display only |
| series_list, series_matches | Series | display only |
| teams_list, team_players, team_schedule, team_results | Teams | display only |
| rankings | Rankings | `ranking_snapshots` |
| top_stats | Stats | display only |
| player_search, player_info, player_batting, player_bowling | Players | display only |
| venue_info | (available through `api_cache.venue`) | - |
| news_list, news_detail | News, Home | display only |

## Error mapping
401 / 403 -> `APIAuthError` · 429 -> `APIRateLimitError` · 404 (after all candidate routes), other 4xx / 5xx, timeouts, connection errors and invalid JSON -> `APIError`. Pages show a friendly message and, for 404, a hint to run `python -m scripts.check_api`.

## Caveat
The routes and field names follow RapidAPI's documentation as known when this was written and were tested with sample payloads, not against your live subscription. If a field differs, only `services/api_parsers.py` needs changing; if a route differs, only `api/endpoints.py`.
