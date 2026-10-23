"""Matches - live, recent and upcoming matches (Cricbuzz API) plus the full archive (real Cricsheet data)."""

from __future__ import annotations

import streamlit as st  # UI

from config import get_settings  # key status
from models.constants import FORMATS  # Test / ODI / T20I
from services import catalog_service as cat  # database queries
from services.card_builders import (
    api_match_to_card,
    db_cards,
    filter_matches,
    group_by_series,
)  # card helpers
from services.sync_service import MatchSyncService  # API -> SQL
from utils import api_cache  # cached API calls
from utils.exceptions import CricbuzzError  # our errors
from utils.theme import caution, page_title, render_match_grid, section  # UI helpers
from utils.ui_helpers import (
    end_page,
    require_data,
    setup_page,
    show_error,
)  # shared helpers

setup_page("Matches")
page_title(
    "Matches", "Live scores, results and fixtures - men's and women's cricket", "live"
)
has_key = get_settings().has_api_key

tab_live, tab_recent, tab_upcoming, tab_archive = st.tabs(
    ["Live", "Recent", "Upcoming", "Archive (all years)"]
)


def api_tab(kind: str, key: str) -> None:
    """One of the three API-backed match lists."""
    if not has_key:
        caution(
            "Add your RAPIDAPI_KEY to the .env file to see live data here. The Archive tab already works with the real match history.",
            "API KEY MISSING",
        )
        return
    scope = st.radio(
        "Show",
        ["All", "International", "Women", "League", "Domestic"],
        horizontal=True,
        key=f"scope_{key}",
    )
    try:
        with st.spinner(f"Loading {kind} matches..."):
            data = filter_matches(api_cache.matches(kind), scope)
    except Exception as exc:  # noqa: BLE001 - show_error handles every case
        show_error(exc, f"Could not load {kind} matches")
        return
    if not data:
        st.info(f"No {kind} matches in this category right now.")
        return
    for index, (series_name, items) in enumerate(
        list(group_by_series(data).items())[:15]
    ):
        section(series_name, "trophy")
        render_match_grid(
            [api_match_to_card(m, force_live=(kind == "live")) for m in items],
            f"{key}_{index}",
        )
    c1, c2 = st.columns([1, 3])
    if c1.button("Save to database", key=f"save_{key}", icon=":material/save:"):
        try:
            result = MatchSyncService().sync(kind)
            c2.success(
                f"Fetched {result.fetched} · new {result.inserted} · updated {result.updated} · linked to history {result.linked} · skipped {result.skipped}"
            )
        except CricbuzzError as exc:
            show_error(exc, "Save failed")


with tab_live:
    api_tab("live", "live")
with tab_recent:
    api_tab("recent", "recent")
with tab_upcoming:
    api_tab("upcoming", "upcoming")

with tab_archive:
    if require_data():
        c1, c2, c3, c4 = st.columns(4)
        gender = c1.selectbox("Competition", ["All", "Men", "Women"], key="arch_g")
        fmt = c2.selectbox("Format", ["All", *FORMATS], key="arch_f")
        years = cat.available_years()
        year = c3.selectbox("Year", ["All", *years], key="arch_y")
        text = c4.text_input(
            "Team / venue / series",
            key="arch_t",
            placeholder="e.g. India, Lord's, Ashes",
        )
        try:
            df = cat.list_matches(
                gender={"Men": "male", "Women": "female"}.get(gender),
                fmt=None if fmt == "All" else fmt,
                year=None if year == "All" else int(year),
                text=text,
                limit=60,
            )
            section(f"{len(df)} most recent matches", "calendar")
            render_match_grid(db_cards(df), "arch")
        except CricbuzzError as exc:
            show_error(exc, "Could not read the match archive")
end_page()
