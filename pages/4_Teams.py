"""Teams - records, squads and head-to-head (real data) plus Cricbuzz team lists."""

from __future__ import annotations

import plotly.express as px  # charts
import streamlit as st  # UI

from config import get_settings  # key status
from services import catalog_service as cat  # database queries
from services.card_builders import api_match_to_card, db_cards  # card helpers
from utils import api_cache  # cached API calls
from utils.exceptions import CricbuzzError  # our errors
from utils.theme import (
    caution,
    format_chip,
    note,
    page_title,
    profile_header,
    render_match_grid,
    render_table,
    section,
    show_chart,
    stat_cards,
)  # UI helpers
from utils.ui_helpers import (
    end_page,
    require_data,
    setup_page,
    show_error,
)  # shared helpers

setup_page("Teams")
page_title(
    "Teams", "Records, squads and head-to-head for every international side", "users"
)
tab_dir, tab_h2h, tab_api = st.tabs(
    ["Teams & records", "Head-to-head", "Cricbuzz teams (API)"]
)

with tab_dir:
    if require_data():
        gender_label = st.radio(
            "Competition", ["Men", "Women"], horizontal=True, key="t_g"
        )
        gender = "male" if gender_label == "Men" else "female"
        try:
            teams = cat.teams_overview(gender)
            teams = teams[teams["played"] > 0]
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
                max_height=300,
            )
            labels = {r.display_name: int(r.team_id) for r in teams.itertuples()}
            chosen = st.selectbox("Open a team", list(labels), key="t_pick")
            tid = labels[chosen]
            profile = cat.team_profile(tid)
            profile_header(
                profile["display_name"],
                [f"{profile['short_name']} · {gender_label}'s international team"],
            )
            record = cat.team_format_record(tid)
            total = record[["played", "won", "lost"]].sum()
            stat_cards(
                [
                    ("Matches", int(total["played"]), "layers"),
                    ("Won", int(total["won"]), "trophy"),
                    ("Lost", int(total["lost"]), "flag"),
                    (
                        "Win %",
                        (
                            round(100 * total["won"] / total["played"], 1)
                            if total["played"]
                            else 0
                        ),
                        "trending-up",
                    ),
                ]
            )
            a, b = st.columns([1, 1])
            with a:
                section("Record by format", "bar-chart")
                render_table(
                    record.rename(
                        columns={"tied_nr_draw": "Tied / NR / Draw", "win_pct": "Win %"}
                    ),
                    max_height=240,
                )
            with b:
                if not record.empty:
                    show_chart(
                        px.bar(
                            record,
                            x="format",
                            y=["won", "lost"],
                            barmode="group",
                            title="Wins and losses by format",
                        ),
                        key=f"rec_{tid}",
                    )
            section("Recent results", "calendar")
            render_match_grid(
                db_cards(cat.list_matches(team_id=tid, limit=6)), "team_recent"
            )
            section("Squad (players active in the last two years)", "user")
            render_table(
                cat.team_squad(tid).drop(columns=["player_id"]), max_height=420
            )
        except CricbuzzError as exc:
            show_error(exc, "Could not read team data")

with tab_h2h:
    if require_data():
        gl = st.radio("Competition", ["Men", "Women"], horizontal=True, key="h_g")
        teams = cat.teams_overview("male" if gl == "Men" else "female")
        teams = teams[teams["played"] > 0]
        labels = {r.display_name: int(r.team_id) for r in teams.itertuples()}
        names = list(labels)
        if len(names) >= 2:
            c1, c2 = st.columns(2)
            a = c1.selectbox("Team A", names, index=0, key="h_a")
            b = c2.selectbox("Team B", names, index=1, key="h_b")
            if a == b:
                st.info("Choose two different teams.")
            else:
                try:
                    h = cat.head_to_head(labels[a], labels[b])
                    stat_cards(
                        [
                            ("Matches", h["played"], "layers"),
                            (f"{a} wins", h["a_wins"], "trophy"),
                            (f"{b} wins", h["b_wins"], "trophy"),
                            (
                                "No result / tied",
                                h["played"] - h["a_wins"] - h["b_wins"],
                                "flag",
                            ),
                        ]
                    )
                    render_table(
                        h["by_format"].rename(
                            columns={
                                "a_wins": f"{a} wins",
                                "b_wins": f"{b} wins",
                                "no_result": "No result",
                            }
                        ),
                        max_height=220,
                    )
                    section("Recent meetings", "calendar")
                    render_match_grid(db_cards(h["recent"].head(6)), "h2h")
                except CricbuzzError as exc:
                    show_error(exc, "Could not compute head-to-head")

with tab_api:
    if not get_settings().has_api_key:
        caution(
            "Add your RAPIDAPI_KEY to the .env file to browse Cricbuzz team lists, squads and fixtures.",
            "API KEY MISSING",
        )
    else:
        category = st.radio(
            "Category",
            ["international", "women", "league", "domestic"],
            horizontal=True,
            format_func=str.title,
            key="t_api_cat",
        )
        try:
            frame = api_cache.teams(category)
        except Exception as exc:  # noqa: BLE001
            show_error(exc, "Could not load teams")
        else:
            if frame.empty:
                st.info("No teams returned.")
            else:
                labels = {
                    f"{r.Team} ({r.Short})": int(r.Id) for r in frame.itertuples()
                }
                chosen = st.selectbox("Team", list(labels), key="t_api_pick")
                tid = labels[chosen]
                sub_players, sub_sched, sub_res = st.tabs(
                    ["Players", "Schedule", "Results"]
                )
                for tab, kind in ((sub_sched, "schedule"), (sub_res, "results")):
                    with tab:
                        try:
                            render_match_grid(
                                [
                                    api_match_to_card(m)
                                    for m in api_cache.team_matches(tid, kind)[:12]
                                ],
                                f"tapi_{kind}",
                            )
                        except Exception as exc:  # noqa: BLE001
                            show_error(exc, f"Could not load {kind}")
                with sub_players:
                    try:
                        render_table(
                            api_cache.team_players(tid).drop(
                                columns=["Id"], errors="ignore"
                            ),
                            empty_message="No players returned.",
                        )
                    except Exception as exc:  # noqa: BLE001
                        show_error(exc, "Could not load players")
end_page()
