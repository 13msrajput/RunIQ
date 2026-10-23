"""Rankings - ICC player and team rankings (Cricbuzz API, men and women) plus the RunIQ Index (computed from real data)."""

from __future__ import annotations

import plotly.express as px  # charts
import streamlit as st  # UI

from api.cricbuzz_client import CricbuzzClient  # API access
from config import get_settings  # key status
from services import catalog_service as cat  # database queries
from services import ranking_service as ranks  # snapshots
from utils.exceptions import CricbuzzError  # our errors
from utils.theme import (
    caution,
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

setup_page("Rankings")
page_title(
    "Rankings", "ICC rankings for players and teams - men's and women's", "award"
)
tab_icc, tab_runiq = st.tabs(["ICC rankings (Cricbuzz API)", "RunIQ Index (computed)"])


@st.cache_data(ttl=3600, show_spinner=False)
def load_ranking(category: str, fmt: str, women: bool):
    """Fetch from the API and store a snapshot (cached for an hour)."""
    return ranks.fetch_and_store(CricbuzzClient(), category, fmt, women)


with tab_icc:
    c1, c2, c3 = st.columns(3)
    competition = c1.radio("Competition", ["Men", "Women"], horizontal=True, key="rk_g")
    category_label = c2.selectbox("Ranking", list(ranks.CATEGORIES), key="rk_c")
    format_label = c3.selectbox("Format", list(ranks.FORMATS), key="rk_f")
    women = competition == "Women"
    category, fmt = ranks.CATEGORIES[category_label], ranks.FORMATS[format_label]
    frame, source = None, ""
    if get_settings().has_api_key:
        try:
            frame, source = (
                load_ranking(category, fmt, women),
                "Live from the Cricbuzz API (snapshot saved to your database)",
            )
        except Exception as exc:  # noqa: BLE001
            show_error(exc, "Could not load live rankings")
    else:
        caution(
            "Add your RAPIDAPI_KEY to the .env file for live ICC rankings. Showing the last saved snapshot if there is one.",
            "API KEY MISSING",
        )
    if frame is None or frame.empty:
        try:
            frame, fetched = ranks.latest_snapshot(category, fmt, women)
            source = f"Saved snapshot from {fetched}" if fetched else ""
        except CricbuzzError as exc:
            show_error(exc, "Could not read the saved snapshot")
            frame = None
    if frame is not None and not frame.empty:
        note(source)
        render_table(frame, max_height=560)
        top = frame.dropna(subset=["Rating"]).head(15)
        if not top.empty:
            color = (
                "Country"
                if "Country" in top.columns
                and top["Country"].astype(str).str.len().gt(0).any()
                else None
            )
            show_chart(
                px.bar(
                    top,
                    x="Name",
                    y="Rating",
                    color=color,
                    title=f"Top {len(top)} - {competition}'s {category_label} ({format_label})",
                ),
                key=f"rk_{category}_{fmt}_{women}",
            )
    else:
        st.info("No ranking data available yet.")

with tab_runiq:
    st.markdown(
        "The **RunIQ Index** ranks players from the real match data stored in your database, using the weighted formula from the project brief: "
        "batting points + bowling points + fielding points. It is *not* the official ICC rating."
    )
    if require_data():
        c1, c2 = st.columns(2)
        gender = c1.radio("Competition", ["Men", "Women"], horizontal=True, key="ri_g")
        fmt_label = c2.selectbox("Format", ["Test", "ODI", "T20I"], key="ri_f")
        try:
            board = cat.runiq_leaderboard(
                fmt_label, "male" if gender == "Men" else "female", 25
            )
            section(f"Top 25 - {gender} {fmt_label}", "trophy")
            render_table(board, max_height=560)
            if not board.empty:
                show_chart(
                    px.bar(
                        board.head(15),
                        x="player",
                        y="runiq_index",
                        color="role",
                        title="RunIQ Index - top 15",
                    ),
                    key=f"ri_{gender}_{fmt_label}",
                )
        except CricbuzzError as exc:
            show_error(exc, "Could not compute the index")
end_page()
