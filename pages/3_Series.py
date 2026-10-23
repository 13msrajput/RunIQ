"""Series - browse every real series (Cricsheet) and the current / upcoming series (Cricbuzz API)."""

from __future__ import annotations

import streamlit as st  # UI

from config import get_settings  # key status
from models.constants import FORMATS  # Test / ODI / T20I
from services import catalog_service as cat  # database queries
from services.card_builders import api_match_to_card, db_cards  # card helpers
from utils import api_cache  # cached API calls
from utils.exceptions import CricbuzzError  # our errors
from utils.theme import (
    caution,
    page_title,
    render_match_grid,
    render_table,
    section,
)  # UI helpers
from utils.ui_helpers import (
    end_page,
    require_data,
    setup_page,
    show_error,
)  # shared helpers

setup_page("Series")
page_title(
    "Series", "Bilateral series and tournaments - past, current and upcoming", "trophy"
)
tab_archive, tab_api = st.tabs(
    ["Archive (real match history)", "Current & upcoming (Cricbuzz API)"]
)

with tab_archive:
    if require_data():
        c1, c2, c3, c4 = st.columns(4)
        gender = c1.selectbox("Competition", ["All", "Men", "Women"], key="s_g")
        fmt = c2.selectbox("Format", ["All", *FORMATS], key="s_f")
        year = c3.selectbox("Year", ["All", *cat.available_years()], key="s_y")
        text = c4.text_input(
            "Search", key="s_t", placeholder="e.g. Ashes, tour of India"
        )
        try:
            df = cat.series_list(
                year=None if year == "All" else int(year),
                gender={"Men": "male", "Women": "female"}.get(gender),
                fmt=None if fmt == "All" else fmt,
                text=text,
                limit=150,
            )
            section(f"{len(df)} series", "calendar")
            render_table(df.drop(columns=["series_id"]), max_height=360)
            if not df.empty:
                labels = {
                    f"{r.series_name} ({r.format}, {r.start_date})": int(r.series_id)
                    for r in df.itertuples()
                }
                chosen = st.selectbox("Open a series", list(labels))
                sid = labels[chosen]
                section("Matches", "live")
                render_match_grid(
                    db_cards(
                        cat.list_matches(series_id=sid, limit=30, newest_first=False)
                    ),
                    "series_db",
                )
                leaders = cat.series_leaders(sid)
                a, b = st.columns(2)
                with a:
                    section("Top run scorers", "bar-chart")
                    render_table(leaders["runs"], max_height=320)
                with b:
                    section("Top wicket takers", "target")
                    render_table(leaders["wickets"], max_height=320)
        except CricbuzzError as exc:
            show_error(exc, "Could not read series")

with tab_api:
    if not get_settings().has_api_key:
        caution(
            "Add your RAPIDAPI_KEY to the .env file to browse current and upcoming series from Cricbuzz.",
            "API KEY MISSING",
        )
    else:
        category = st.radio(
            "Category",
            ["international", "league", "domestic", "women"],
            horizontal=True,
            format_func=str.title,
        )
        try:
            frame = api_cache.series_list(category)
        except Exception as exc:  # noqa: BLE001
            show_error(exc, "Could not load series")
        else:
            render_table(
                frame.drop(columns=["Id"], errors="ignore"),
                empty_message="No series returned.",
                max_height=360,
            )
            if not frame.empty:
                labels = {
                    f"{r.Series} ({r.Start})": int(r.Id)
                    for r in frame.itertuples()
                    if r.Id
                }
                chosen = st.selectbox(
                    "Open a series", list(labels), key="api_series_pick"
                )
                try:
                    items = api_cache.series_matches(labels[chosen])
                except Exception as exc:  # noqa: BLE001
                    show_error(exc, "Could not load the series matches")
                else:
                    section("Matches", "live")
                    render_match_grid(
                        [api_match_to_card(m) for m in items], "series_api"
                    )
end_page()
