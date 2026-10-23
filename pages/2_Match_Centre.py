"""Match Centre - scorecard, charts, squads and (for API matches) live commentary."""

from __future__ import annotations

import pandas as pd  # squads table
import plotly.express as px  # charts
import streamlit as st  # UI

from services import catalog_service as cat  # database queries
from utils import api_cache  # cached API calls
from config import get_settings  # key status
from utils.exceptions import CricbuzzError  # our errors
from utils.theme import (
    esc,
    format_chip,
    note,
    page_title,
    pill,
    render_table,
    section,
    show_chart,
    stat_cards,
    team_bar,
)  # UI helpers
from utils.ui_helpers import (
    end_page,
    require_data,
    setup_page,
    show_error,
)  # shared helpers

setup_page("Match Centre")
page_title("Match Centre", "Full scorecard, charts and squads", "target")
ref = st.session_state.get("match_ref")


def pick_database_match() -> None:
    """Let the user choose a recent archive match when none was selected."""
    if not require_data():
        return
    df = cat.list_matches(limit=80)
    labels = {
        f"{r.match_date} · {r.team1} vs {r.team2} · {r.match_desc}": int(r.match_id)
        for r in df.itertuples()
    }
    if labels:
        choice = st.selectbox("Choose a match from the archive", list(labels))
        if st.button("Open match", icon=":material/open_in_new:"):
            st.session_state["match_ref"] = {
                "src": "db",
                "id": labels[choice],
                "title": choice,
            }
            st.rerun()


def show_db_match(match_id: int) -> None:
    """Scorecard + charts built from the stored ball-by-ball data."""
    header = cat.match_header(match_id)
    if not header:
        st.warning("This match no longer exists in the database.")
        return
    st.markdown(
        f'<div class="cb-panel"><div style="display:flex;justify-content:space-between;align-items:center">'
        f'<b>{esc(header["match_desc"])} · {esc(header["series_name"] or "")}</b>{format_chip(header["match_format"])}</div>'
        f'<div class="cb-team"><span>{esc(header["team1"])}</span><span>{esc(header["score1"])}</span></div>'
        f'<div class="cb-team"><span>{esc(header["team2"])}</span><span>{esc(header["score2"])}</span></div>'
        f'<div class="cb-status">{esc(header["result_text"])}</div>'
        f'<div class="cb-note">{esc(header["venue_name"])}, {esc(header["city"])} · {esc(header["match_date"])}'
        f'{" · Toss: " + esc(header["toss_text"]) if header["toss_text"] else ""}{" · Player of the match: " + esc(header["player_of_match"]) if header.get("player_of_match") else ""}</div></div>',
        unsafe_allow_html=True,
    )
    tab_card, tab_charts, tab_squads = st.tabs(["Scorecard", "Charts", "Squads"])
    with tab_card:
        for inn in cat.match_scorecard(match_id):
            pill(f"{inn['team']} · Innings {inn['innings_no']}")
            team_bar(inn["team"], inn["total"])
            render_table(inn["batting"], empty_message="No batting data.")
            note(
                f"Extras: {inn['extras']}"
                + (f" · Target: {inn['target']}" if inn["target"] else "")
                + (
                    f" · Did not bat: {', '.join(inn['did_not_bat'])}"
                    if inn["did_not_bat"]
                    else ""
                )
            )
            if inn["fow"]:
                note("Fall of wickets: " + inn["fow"])
            render_table(inn["bowling"], empty_message="No bowling data.")
    with tab_charts:
        overs = cat.match_over_data(match_id)
        if overs.empty:
            st.info("No over-by-over data for this match.")
        else:
            show_chart(
                px.line(
                    overs,
                    x="over",
                    y="cumulative",
                    color="innings",
                    markers=False,
                    title="Worm - cumulative runs",
                ),
                key=f"worm_{match_id}",
            )
            show_chart(
                px.bar(
                    overs,
                    x="over",
                    y="runs",
                    color="innings",
                    barmode="group",
                    title="Manhattan - runs per over",
                ),
                key=f"man_{match_id}",
            )
            show_chart(
                px.line(
                    overs, x="over", y="run_rate", color="innings", title="Run rate"
                ),
                key=f"rr_{match_id}",
            )
    with tab_squads:
        squads = cat.match_squads(match_id)
        cols = st.columns(max(len(squads), 1))
        for col, (team, frame) in zip(cols, squads.items()):
            with col:
                section(team, "users")
                render_table(frame, max_height=420)


def show_api_match(match_id: int, title: str) -> None:
    """Live scorecard / commentary from the Cricbuzz API."""
    if not get_settings().has_api_key:
        st.warning(
            "This match comes from the Cricbuzz API. Add RAPIDAPI_KEY to .env to open it."
        )
        return
    st.markdown(
        f'<div class="cb-panel"><b>{esc(title)}</b> <span class="cb-note">Cricbuzz match id {esc(match_id)}</span></div>',
        unsafe_allow_html=True,
    )
    if st.button("Refresh", icon=":material/refresh:"):
        st.cache_data.clear()
    tab_card, tab_comm, tab_info = st.tabs(["Scorecard", "Commentary", "Info & squads"])
    with tab_card:
        try:
            innings = api_cache.scorecard(int(match_id))
        except Exception as exc:  # noqa: BLE001
            show_error(exc, "Could not load the scorecard")
        else:
            if not innings:
                st.info(
                    "The scorecard is not available yet (the match may not have started)."
                )
            for inn in innings:
                pill(f"{inn.team_name} · Innings {inn.innings_id}")
                team_bar(inn.team_name, inn.total)
                render_table(inn.batting, empty_message="No batting data yet.")
                note(
                    f"Extras: {inn.extras}"
                    + (f" · Run rate: {inn.run_rate}" if inn.run_rate else "")
                )
                render_table(inn.bowling, empty_message="No bowling data yet.")
                if not inn.fow.empty:
                    with st.expander("Fall of wickets and partnerships"):
                        render_table(inn.fow)
                        render_table(inn.partnerships)
    with tab_comm:
        try:
            entries = api_cache.commentary(int(match_id))
        except Exception as exc:  # noqa: BLE001
            show_error(exc, "Could not load commentary")
        else:
            if not entries:
                st.info("No commentary yet.")
            for e in entries:
                badge = (
                    f'<span class="e {esc(e["event"])}">{esc(e["event"])}</span><br>'
                    if e["event"] in ("FOUR", "SIX", "WICKET")
                    else ""
                )
                st.markdown(
                    f'<div class="cb-comm"><div class="o">{esc(e["over"] or "")}</div><div>{badge}<div class="x">{esc(e["text"])}</div></div></div>',
                    unsafe_allow_html=True,
                )
    with tab_info:
        try:
            info = api_cache.match_info(int(match_id))
        except Exception as exc:  # noqa: BLE001
            show_error(exc, "Could not load match info")
        else:
            stat_cards(
                [
                    ("Series", info.get("series") or "-"),
                    ("Venue", info.get("venue") or "-"),
                    ("Toss", info.get("toss") or "-"),
                ]
            )
            if info.get("umpires"):
                note(
                    "Umpires: "
                    + ", ".join(info["umpires"])
                    + (f" · Referee: {info['referee']}" if info.get("referee") else "")
                )
            for team, players in info.get("squads", {}).items():
                section(team, "users")
                render_table(
                    pd.DataFrame(players), empty_message="Squad not announced yet."
                )


try:
    if not ref:
        st.info("Open a match from the Matches page, or pick one below.")
        pick_database_match()
    elif ref.get("src") == "db":
        show_db_match(int(ref["id"]))
        if st.button("Choose another match", icon=":material/swap_horiz:"):
            st.session_state.pop("match_ref", None)
            st.rerun()
    else:
        show_api_match(int(ref["id"]), ref.get("title", "Match"))
        if st.button("Choose another match", icon=":material/swap_horiz:"):
            st.session_state.pop("match_ref", None)
            st.rerun()
except CricbuzzError as exc:
    show_error(exc, "Could not open the match")
end_page()
