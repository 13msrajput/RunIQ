"""Players - search every real international player, full career profile, plus live Cricbuzz profiles."""

from __future__ import annotations

import pandas as pd  # profile table
import plotly.express as px  # charts
import streamlit as st  # UI

from config import get_settings  # key status
from models.constants import ROLES  # playing roles
from services import catalog_service as cat  # database queries
from utils import api_cache  # cached API calls
from utils.exceptions import CricbuzzError  # our errors
from utils.theme import (
    caution,
    format_chip,
    note,
    page_title,
    profile_header,
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

setup_page("Players")
page_title(
    "Players",
    "Present and past international players with full career statistics",
    "user",
)
tab_db, tab_api = st.tabs(
    ["Player search (real match history)", "Live profile (Cricbuzz API)"]
)

with tab_db:
    if require_data():
        c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
        text = c1.text_input("Name", placeholder="e.g. Kohli, Mandhana", key="p_text")
        gender_label = c2.selectbox(
            "Competition", ["All", "Men", "Women"], key="p_gender"
        )
        role = c3.selectbox("Role", ["All", *ROLES], key="p_role")
        team_text = c4.text_input("Team", placeholder="e.g. India", key="p_team")
        active = c5.checkbox("Active only", value=True, key="p_active")
        try:
            team_id = None
            if team_text.strip():
                teams = cat.teams_overview(None)
                match = teams[
                    teams["team_name"]
                    .str.lower()
                    .str.contains(team_text.strip().lower())
                ]
                if match.empty:
                    st.warning("No team with that name.")
                team_id = int(match.iloc[0]["team_id"]) if len(match) == 1 else None
            df = cat.search_players(
                text,
                gender={"Men": "male", "Women": "female"}.get(gender_label),
                team_id=team_id,
                role=None if role == "All" else role,
                active_only=active,
                limit=150,
            )
            section(f"{len(df)} players", "users")
            render_table(
                df.drop(columns=["player_id", "gender", "is_active"]), max_height=300
            )
            if not df.empty:
                labels = {
                    f"{r.full_name} · {r.team} · {r.role} (#{r.player_id})": int(
                        r.player_id
                    )
                    for r in df.itertuples()
                }  # id keeps same-name players apart
                chosen = st.selectbox(
                    "Open a player profile", list(labels), key="p_pick"
                )
                pid = labels[chosen]
                p = cat.player_profile(pid)
                career = cat.player_career(pid)
                active_years = (
                    f"{str(p.get('first_match_date'))[:4]} - {str(p.get('last_match_date'))[:4]}"
                    if p.get("first_match_date")
                    else ""
                )
                profile_header(
                    p["full_name"],
                    [
                        f"{p['team']} · {p['playing_role']} · {'Men' if p['gender'] == 'male' else 'Women'}",
                        f"International career {active_years}"
                        + (
                            "  (active)"
                            if p.get("is_active")
                            else "  (retired / not recently selected)"
                        ),
                    ],
                )
                if not career.empty:
                    stat_cards(
                        [
                            ("Matches", int(career["matches"].sum()), "layers"),
                            ("Runs", int(career["runs"].sum()), "bar-chart"),
                            ("Wickets", int(career["wickets"].sum()), "target"),
                            ("Centuries", int(career["100s"].sum()), "award"),
                            ("Catches", int(career["ct"].sum()), "shield"),
                        ]
                    )
                    section("Career statistics", "trending-up")
                    render_table(career, max_height=240)
                    note(
                        "Role is derived from match data (batting position, bowling share, stumpings). Cricsheet does not record batting / bowling style or birth dates."
                    )
                    a, b = st.columns(2)
                    by_year = cat.player_runs_by_year(pid)
                    with a:
                        if not by_year.empty:
                            show_chart(
                                px.bar(
                                    by_year,
                                    x="year",
                                    y="runs",
                                    color="format",
                                    title="Runs per year",
                                ),
                                key=f"year_{pid}",
                            )
                    with b:
                        dis = cat.player_dismissals(pid)
                        if not dis.empty:
                            show_chart(
                                px.pie(
                                    dis,
                                    names="how_out",
                                    values="times",
                                    title="How dismissed",
                                ),
                                key=f"dis_{pid}",
                            )
                    section("Recent innings", "clock")
                    render_table(cat.player_recent_innings(pid, 15), max_height=380)
                    a, b = st.columns(2)
                    with a:
                        section("Against opposition", "flag")
                        render_table(cat.player_vs_opposition(pid), max_height=360)
                    with b:
                        section("Best bowling", "target")
                        render_table(
                            cat.player_best_bowling(pid),
                            empty_message="This player has not bowled.",
                            max_height=360,
                        )
        except CricbuzzError as exc:
            show_error(exc, "Could not read player data")

with tab_api:
    if not get_settings().has_api_key:
        caution(
            "Add your RAPIDAPI_KEY to the .env file to look up live Cricbuzz player profiles.",
            "API KEY MISSING",
        )
    else:
        name = st.text_input(
            "Search Cricbuzz players", placeholder="e.g. Kohli", key="p_api_name"
        )
        if name.strip():
            try:
                found = api_cache.player_search(name.strip())
            except Exception as exc:  # noqa: BLE001
                show_error(exc, "Search failed")
            else:
                if found.empty:
                    st.info("No players found.")
                else:
                    render_table(found.drop(columns=["Id"]), max_height=240)
                    labels = {
                        f"{r.Name} · {r.Team}": int(r.Id)
                        for r in found.itertuples()
                        if r.Id
                    }
                    chosen = st.selectbox(
                        "Open profile", list(labels), key="p_api_pick"
                    )
                    pid = labels[chosen]
                    try:
                        info = api_cache.player_info(pid)
                        profile_header(
                            info.get("Name", chosen),
                            [
                                info.get("International team", ""),
                                info.get("Role", ""),
                                info.get("Born", ""),
                            ],
                        )
                        render_table(
                            pd.DataFrame(
                                [{k: v for k, v in info.items() if k != "Bio"}]
                            ),
                            max_height=120,
                        )
                        if info.get("Bio"):
                            st.markdown(
                                info["Bio"][:1500]
                            )  # plain text only (HTML was stripped by the parser)
                        for kind in ("batting", "bowling"):
                            section(
                                f"Career {kind}",
                                "bar-chart" if kind == "batting" else "target",
                            )
                            render_table(
                                api_cache.player_table(pid, kind),
                                empty_message=f"No {kind} table returned.",
                            )
                    except Exception as exc:  # noqa: BLE001
                        show_error(exc, "Could not load the profile")
end_page()
