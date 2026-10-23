"""Streamlit-cached wrappers around the Cricbuzz API (saves your RapidAPI quota).

Each function returns plain, picklable data. Exceptions are NOT cached, so a failed call is retried next time.
"""

from __future__ import annotations

import pandas as pd  # tables
import streamlit as st  # caching

from api.cricbuzz_client import CricbuzzClient  # API access
from services import api_parsers as P  # JSON -> objects


def _client() -> CricbuzzClient:
    return CricbuzzClient()


@st.cache_data(ttl=45, show_spinner=False)
def matches(kind: str) -> list[P.LiveMatch]:
    """'live', 'recent' or 'upcoming' matches."""
    client = _client()
    payload = {
        "live": client.get_live_matches,
        "recent": client.get_recent_matches,
        "upcoming": client.get_upcoming_matches,
    }[kind]()
    return P.parse_matches_response(payload)


@st.cache_data(ttl=45, show_spinner=False)
def scorecard(match_id: int) -> list[P.InningsScorecard]:
    return P.parse_scorecard(_client().get_scorecard(match_id))


@st.cache_data(ttl=30, show_spinner=False)
def commentary(match_id: int) -> list[dict]:
    return P.parse_commentary(_client().get_commentary(match_id))


@st.cache_data(ttl=600, show_spinner=False)
def match_info(match_id: int) -> dict:
    return P.parse_match_info(_client().get_match_info(match_id))


@st.cache_data(ttl=1800, show_spinner=False)
def series_list(category: str) -> pd.DataFrame:
    return P.parse_series_list(_client().get_series_list(category))


@st.cache_data(ttl=900, show_spinner=False)
def series_matches(series_id: int) -> list[P.LiveMatch]:
    return P.parse_any_matches(_client().get_series_matches(series_id))


@st.cache_data(ttl=3600, show_spinner=False)
def teams(category: str) -> pd.DataFrame:
    return P.parse_teams_list(_client().get_teams(category))


@st.cache_data(ttl=3600, show_spinner=False)
def team_players(team_id: int) -> pd.DataFrame:
    return P.parse_team_players(_client().get_team_players(team_id))


@st.cache_data(ttl=900, show_spinner=False)
def team_matches(team_id: int, kind: str) -> list[P.LiveMatch]:
    client = _client()
    return P.parse_any_matches(
        client.get_team_schedule(team_id)
        if kind == "schedule"
        else client.get_team_results(team_id)
    )


@st.cache_data(ttl=3600, show_spinner=False)
def venue(venue_id: int) -> dict:
    return P.parse_venue(_client().get_venue(venue_id))


@st.cache_data(ttl=3600, show_spinner=False)
def top_stats(stats_type: str) -> pd.DataFrame:
    return P.parse_table_payload(_client().get_top_stats(stats_type))


@st.cache_data(ttl=600, show_spinner=False)
def player_search(name: str) -> pd.DataFrame:
    return P.parse_player_search(_client().search_player(name))


@st.cache_data(ttl=3600, show_spinner=False)
def player_info(player_id: int) -> dict:
    return P.parse_player_info(_client().get_player_info(player_id))


@st.cache_data(ttl=3600, show_spinner=False)
def player_table(player_id: int, kind: str) -> pd.DataFrame:
    client = _client()
    return P.parse_table_payload(
        client.get_player_batting(player_id)
        if kind == "batting"
        else client.get_player_bowling(player_id)
    )


@st.cache_data(ttl=600, show_spinner=False)
def news() -> list[dict]:
    return P.parse_news_list(_client().get_news())


@st.cache_data(ttl=1800, show_spinner=False)
def news_detail(news_id: int) -> dict:
    return P.parse_news_detail(_client().get_news_detail(news_id))
