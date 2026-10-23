"""Stats & Records - batting, bowling, fielding, team and venue records computed from real match data."""

from __future__ import annotations

import plotly.express as px  # charts
import streamlit as st  # UI

from config import get_settings  # key status
from models.constants import FORMATS  # Test / ODI / T20I
from services import catalog_service as cat  # database queries
from utils import api_cache  # cached API calls
from utils.exceptions import CricbuzzError  # our errors
from utils.theme import (
    note,
    page_title,
    render_table,
    section,
    show_chart,
)  # UI helpers
from utils.ui_helpers import (
    end_page,
    require_data,
    setup_page,
    show_error,
)  # shared helpers

setup_page("Stats")
page_title(
    "Stats & Records",
    "Leaders and records from every international match in your database",
    "bar-chart",
)
if not require_data():
    end_page()
    st.stop()

c1, c2, c3 = st.columns(3)
fmt_label = c1.selectbox("Format", ["All formats", *FORMATS], key="st_f")
gender_label = c2.selectbox(
    "Competition", ["Men and women", "Men", "Women"], key="st_g"
)
years = cat.available_years()
since_label = c3.selectbox("Since year", ["All time", *years], key="st_y")
fmt = None if fmt_label == "All formats" else fmt_label
gender = {"Men": "male", "Women": "female"}.get(gender_label)
since = None if since_label == "All time" else int(since_label)

tab_bat, tab_bowl, tab_field, tab_team, tab_venue, tab_api = st.tabs(
    ["Batting", "Bowling", "Fielding", "Teams", "Venues", "Cricbuzz leaders (API)"]
)


def leaderboard(tab, kinds, loader, chart_x, chart_y, key):
    """Selectbox + table + bar chart for one family of records."""
    with tab:
        kind = st.selectbox("Record", kinds, key=f"{key}_kind")
        try:
            df = loader(kind, fmt, gender, since, 25)
        except CricbuzzError as exc:
            show_error(exc, "Could not compute the records")
            return
        render_table(df, max_height=520)
        if not df.empty and chart_x in df.columns and chart_y in df.columns:
            show_chart(
                px.bar(df.head(12), x=chart_x, y=chart_y, title=f"{kind} - top 12"),
                key=f"{key}_chart",
            )


leaderboard(tab_bat, cat.BATTING_KINDS, cat.batting_records, "player", "runs", "bat")
leaderboard(
    tab_bowl, cat.BOWLING_KINDS, cat.bowling_records, "player", "wickets", "bowl"
)
leaderboard(
    tab_field, cat.FIELDING_KINDS, cat.fielding_records, "player", "catches", "field"
)
with tab_team:
    kind = st.selectbox("Record", cat.TEAM_KINDS, key="team_kind")
    try:
        df = cat.team_records(kind, fmt, gender, since, 25)
        render_table(df, max_height=520)
    except CricbuzzError as exc:
        show_error(exc, "Could not compute team records")
with tab_venue:
    try:
        countries = cat.venue_countries()
        country = st.selectbox("Country", ["All", *countries], key="venue_country")
        text = st.text_input("Search venue or city", key="venue_text")
        df = cat.venues_overview(None if country == "All" else country, text)
        note(
            "Capacity figures come from a static reference list (approximate). Average first-innings score and bat-first win % are computed from real matches."
        )
        render_table(df.drop(columns=["venue_id"]), max_height=520)
        if not df.empty:
            show_chart(
                px.scatter(
                    df.head(60),
                    x="avg_first_innings",
                    y="bat_first_win_pct",
                    size="matches",
                    hover_name="venue_name",
                    title="Scoring pace vs bat-first success",
                ),
                key="venue_scatter",
            )
    except CricbuzzError as exc:
        show_error(exc, "Could not compute venue statistics")
with tab_api:
    if not get_settings().has_api_key:
        st.info(
            "Add RAPIDAPI_KEY to the .env file to see the Cricbuzz career leaderboards."
        )
    else:
        from services.stats_labels import TOP_STATS_TYPES  # label -> statsType

        label = st.selectbox("Leaderboard", list(TOP_STATS_TYPES), key="api_top")
        try:
            table = api_cache.top_stats(TOP_STATS_TYPES[label])
            render_table(table, empty_message="No data returned for this leaderboard.")
        except Exception as exc:  # noqa: BLE001
            show_error(exc, "Could not load the leaderboard")
end_page()
