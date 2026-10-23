"""RunIQ - Home page (entry point: ``streamlit run main.py``)."""

from __future__ import annotations

import streamlit as st  # UI

from config import get_settings  # key status
from services import catalog_service as cat  # database queries
from services.card_builders import (
    api_match_to_card,
    db_cards,
    filter_matches,
)  # card helpers
from utils import api_cache  # cached API calls
from utils.branding import APP_NAME, APP_TAGLINE  # branding
from utils.db_connection import create_schema, table_counts  # DB helpers
from utils.exceptions import CricbuzzError  # our errors
from utils.theme import (
    caution,
    hero,
    news_card,
    render_strip,
    render_table,
    section,
    stat_cards,
)  # UI helpers
from utils.ui_helpers import end_page, setup_page, show_error  # shared helpers

setup_page("Home")
try:
    create_schema()  # idempotent: makes sure the tables exist on first launch
    counts = table_counts()
except CricbuzzError as exc:
    show_error(exc, "Database setup")
    end_page()
    st.stop()

hero(f"{APP_NAME}", f"{APP_TAGLINE} - men's and women's international cricket")
has_key = get_settings().has_api_key

# ------------------------------------------------------------ match strip (live when possible)
section("Matches", "live")
shown = False
if has_key:
    try:
        live = api_cache.matches("live")
        recent = api_cache.matches("recent")
        pool = [
            m
            for m in filter_matches(live, "International")
            + filter_matches(live, "Women")
        ][:6]
        pool += [
            m
            for m in filter_matches(recent, "International")
            + filter_matches(recent, "Women")
        ][: max(0, 10 - len(pool))]
        if pool:
            render_strip(
                [
                    api_match_to_card(
                        m, force_live=(i < len([x for x in live if x in pool]))
                    )
                    for i, m in enumerate(pool)
                ]
            )
            shown = True
    except Exception as exc:  # noqa: BLE001
        show_error(exc, "Live matches unavailable")
if not shown and counts.get("matches", 0):
    try:
        render_strip(db_cards(cat.list_matches(limit=10)))
        shown = True
    except CricbuzzError as exc:
        show_error(exc, "Could not load matches")
if not shown:
    caution(
        "No matches to show yet. Import the real match history (Data & Settings page) and/or add your RapidAPI key to see live scores here.",
        "GETTING STARTED",
    )

# ------------------------------------------------------------ quick access
with st.container(key="quick"):
    quick = st.columns(6)
    for col, (path, label, symbol) in zip(
        quick,
        [
            ("pages/1_Matches.py", "Live & results", ":material/sensors:"),
            ("pages/5_Players.py", "Players", ":material/person:"),
            ("pages/4_Teams.py", "Teams", ":material/groups:"),
            ("pages/6_Rankings.py", "Rankings", ":material/emoji_events:"),
            (
                "pages/7_Stats_and_Records.py",
                "Stats & records",
                ":material/query_stats:",
            ),
            ("pages/9_SQL_Analytics.py", "SQL analytics", ":material/database:"),
        ],
    ):
        col.page_link(path, label=label, icon=symbol)

if counts.get("matches", 0) == 0:
    with st.container(key="cta"):  # the one action a new user needs
        st.page_link(
            "pages/12_Data_and_Settings.py",
            label="Import the real match history (Data & Settings)",
            icon=":material/download:",
        )
    end_page()
    st.stop()

# ------------------------------------------------------------ data status
status = cat.data_status()
stat_cards(
    [
        ("Matches", f"{int(status['matches']):,}", "layers"),
        ("Players", f"{int(status['players']):,}", "users"),
        ("Teams", int(status["teams"]), "flag"),
        ("Venues", int(status["venues"]), "map-pin"),
        ("Series", f"{int(status['series']):,}", "trophy"),
    ]
)

# ------------------------------------------------------------ standings + leaders
try:
    left, right = st.columns(2)
    with left:
        section("Most successful men's teams (all formats)", "trophy")
        teams = cat.teams_overview("male")
        teams = (
            teams[teams["played"] >= 30]
            .sort_values("win_pct", ascending=False)
            .head(10)
        )
        render_table(
            teams[["display_name", "played", "won", "lost", "win_pct"]].rename(
                columns={
                    "display_name": "Team",
                    "played": "P",
                    "won": "W",
                    "lost": "L",
                    "win_pct": "Win %",
                }
            ),
            max_height=420,
        )
    with right:
        section("Top run scorers (all formats)", "bar-chart")
        render_table(
            cat.batting_records("Most runs", None, None, None, 10)[
                ["player", "team", "inns", "runs", "avg", "hundreds"]
            ].rename(
                columns={
                    "inns": "Inns",
                    "runs": "Runs",
                    "avg": "Avg",
                    "hundreds": "100s",
                }
            ),
            max_height=420,
        )
except CricbuzzError as exc:
    show_error(exc, "Could not load statistics")

# ------------------------------------------------------------ news
if has_key:
    section("Latest news", "news")
    try:
        for story in api_cache.news()[:3]:
            when = (
                story["published"].strftime("%d %b %Y")
                if story.get("published")
                else ""
            )
            news_card(
                story["headline"],
                story["intro"],
                " · ".join(p for p in (story.get("context"), when) if p),
            )
    except Exception as exc:  # noqa: BLE001
        show_error(exc, "News unavailable")
end_page()
