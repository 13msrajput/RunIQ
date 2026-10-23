"""Manage Data - validated CRUD (create, read, update, delete) for players, matches, career stats and venues."""

from __future__ import annotations

from datetime import date

import streamlit as st  # UI

from models.constants import (
    BATTING_STYLES,
    BOWLING_STYLES,
    FORMATS,
    MATCH_STATUSES,
    RESULT_TYPES,
    ROLES,
    TOSS_DECISIONS,
    VICTORY_TYPES,
)  # allowed values
from services import catalog_service as cat  # database queries
from services.career_stats_service import CareerStatsService  # career CRUD
from services.match_service import MatchService  # match CRUD
from services.player_service import PlayerService  # player CRUD
from services.venue_service import VenueService  # venue CRUD
from utils.db_connection import run_query  # lookups
from utils.exceptions import CricbuzzError  # our errors
from utils.theme import note, page_title, render_table, section  # UI helpers
from utils.ui_helpers import (
    end_page,
    require_data,
    setup_page,
    show_error,
)  # shared helpers

setup_page("Manage Data")
page_title(
    "Manage Data (CRUD)",
    "Add, view, edit and delete records with validation - every action runs in a database transaction",
    "edit",
)
if not require_data():
    end_page()
    st.stop()

players, matches, career, venues_svc = (
    PlayerService(),
    MatchService(),
    CareerStatsService(),
    VenueService(),
)


def teams_map(gender: str | None = None) -> dict[str, int]:
    """{display name: team_id} (optionally one gender)."""
    sql, params = "SELECT team_id, display_name FROM teams", {}
    if gender:
        sql, params = sql + " WHERE gender = :g", {"g": gender}
    frame = run_query(sql + " ORDER BY display_name", params)
    return {r.display_name: int(r.team_id) for r in frame.itertuples()}


def player_picker(key: str, label: str = "Find a player") -> int | None:
    """Search box + select box (the player table is too big for one giant dropdown)."""
    text = st.text_input(
        label, key=f"{key}_text", placeholder="type part of a name, e.g. Kohli"
    )
    if not text.strip():
        st.caption("Type a name to search.")
        return None
    found = cat.search_players(text, limit=40)
    if found.empty:
        st.warning("No player found.")
        return None
    labels = {
        f"{r.full_name} · {r.team} · {r.role} (#{r.player_id})": int(r.player_id)
        for r in found.itertuples()
    }
    return labels[st.selectbox("Choose", list(labels), key=f"{key}_pick")]


def venue_picker(key: str) -> int | None:
    text = st.text_input(
        "Find a venue", key=f"{key}_text", placeholder="e.g. Eden, Lord's"
    )
    if not text.strip():
        st.caption("Type a venue or city to search.")
        return None
    found = cat.venues_overview(None, text, 40)
    if found.empty:
        st.warning("No venue found.")
        return None
    labels = {
        f"{r.venue_name} · {r.city} (#{r.venue_id})": int(r.venue_id)
        for r in found.itertuples()
    }
    return labels[st.selectbox("Choose", list(labels), key=f"{key}_pick")]


def run_action(action, success: str) -> None:
    """Execute ``action`` and show a friendly result either way."""
    try:
        action()
    except CricbuzzError as exc:
        show_error(exc)
    except Exception as exc:  # noqa: BLE001 - unexpected bug
        show_error(exc, "Unexpected error")
    else:
        st.success(success)
        st.cache_data.clear()  # other pages must see the change


tab_players, tab_matches, tab_career, tab_venues = st.tabs(
    ["Players", "Matches", "Career stats", "Venues"]
)

# ================================================================== PLAYERS
with tab_players:
    op = st.radio(
        "Operation", ["Read", "Create", "Update", "Delete"], horizontal=True, key="p_op"
    )
    if op == "Read":
        text = st.text_input("Search by name", key="p_search")
        try:
            render_table(
                cat.search_players(text, limit=200).drop(
                    columns=["gender", "is_active"]
                ),
                max_height=420,
            )
        except CricbuzzError as exc:
            show_error(exc)
    elif op == "Create":
        teams = teams_map()
        with st.form("create_player", clear_on_submit=True):
            name = st.text_input("Full name *")
            team = st.selectbox("Team *", list(teams))
            role = st.selectbox("Playing role *", ROLES)
            bat = st.selectbox("Batting style", ["", *BATTING_STYLES])
            bowl = st.selectbox("Bowling style", ["", *BOWLING_STYLES])
            dob = st.date_input(
                "Date of birth",
                value=date(2000, 1, 1),
                min_value=date(1930, 1, 1),
                max_value=date.today(),
            )
            if st.form_submit_button("Add player", icon=":material/person_add:"):
                run_action(
                    lambda: players.create(
                        {
                            "full_name": name,
                            "team_id": teams[team],
                            "playing_role": role,
                            "batting_style": bat,
                            "bowling_style": bowl,
                            "date_of_birth": dob,
                            "is_active": True,
                        }
                    ),
                    "Player added.",
                )
    elif op == "Update":
        pid = player_picker("p_upd")
        current = players.get({"player_id": pid}) if pid else None
        if current:
            teams = teams_map()
            id_to_team = {v: k for k, v in teams.items()}
            with st.form("update_player"):
                name = st.text_input("Full name", value=current["full_name"])
                team = st.selectbox(
                    "Team",
                    list(teams),
                    index=list(teams).index(id_to_team[current["team_id"]]),
                )
                role = st.selectbox(
                    "Playing role", ROLES, index=ROLES.index(current["playing_role"])
                )
                bat = st.selectbox(
                    "Batting style",
                    ["", *BATTING_STYLES],
                    index=(
                        ["", *BATTING_STYLES].index(current["batting_style"])
                        if current["batting_style"] in BATTING_STYLES
                        else 0
                    ),
                )
                bowl = st.selectbox(
                    "Bowling style",
                    ["", *BOWLING_STYLES],
                    index=(
                        ["", *BOWLING_STYLES].index(current["bowling_style"])
                        if current["bowling_style"] in BOWLING_STYLES
                        else 0
                    ),
                )
                active = st.checkbox("Active", value=bool(current["is_active"]))
                if st.form_submit_button("Save changes", icon=":material/save:"):
                    run_action(
                        lambda: players.update(
                            {"player_id": pid},
                            {
                                "full_name": name,
                                "team_id": teams[team],
                                "playing_role": role,
                                "batting_style": bat,
                                "bowling_style": bowl,
                                "is_active": active,
                            },
                        ),
                        "Player updated.",
                    )
    else:
        pid = player_picker("p_del")
        st.warning(
            "Deleting a player also deletes their match performances and career stats."
        )
        confirm = st.checkbox("I understand - delete this player", key="p_del_ok")
        if st.button(
            "Delete player", disabled=not (confirm and pid), icon=":material/delete:"
        ):
            run_action(lambda: players.delete({"player_id": pid}), "Player deleted.")

# ================================================================== MATCHES
with tab_matches:
    op = st.radio(
        "Operation", ["Read", "Create", "Update", "Delete"], horizontal=True, key="m_op"
    )
    if op == "Read":
        text = st.text_input("Search team / venue / series", key="m_search")
        try:
            frame = cat.list_matches(text=text, limit=100)
            render_table(
                frame[
                    [
                        "match_id",
                        "match_date",
                        "match_desc",
                        "match_format",
                        "team1",
                        "team2",
                        "result_text",
                        "venue_name",
                    ]
                ],
                max_height=460,
            )
        except CricbuzzError as exc:
            show_error(exc)
    elif op == "Create":
        gender_label = st.radio(
            "Competition", ["Men", "Women"], horizontal=True, key="m_cg"
        )
        teams = teams_map("male" if gender_label == "Men" else "female")
        venue_id = venue_picker("m_cv")
        with st.form("create_match", clear_on_submit=True):
            desc = st.text_input("Description * (e.g. 1st ODI)")
            fmt = st.selectbox("Format *", FORMATS)
            names = list(teams)
            t1 = st.selectbox("Team 1 *", names)
            t2 = st.selectbox("Team 2 *", names, index=min(1, len(names) - 1))
            when = st.date_input("Match date *", value=date.today())
            status = st.selectbox("Status", MATCH_STATUSES)
            toss_w = st.selectbox("Toss winner", ["", t1, t2])
            toss_d = st.selectbox("Toss decision", ["", *TOSS_DECISIONS])
            winner = st.selectbox("Winner (completed matches)", ["", t1, t2])
            margin = st.number_input(
                "Victory margin", min_value=0, max_value=1000, value=0
            )
            vtype = st.selectbox("Victory type", ["", *VICTORY_TYPES])
            if st.form_submit_button("Add match", icon=":material/add:"):
                run_action(
                    lambda: matches.create(
                        {
                            "match_desc": desc,
                            "match_format": fmt,
                            "team1_id": teams[t1],
                            "team2_id": teams[t2],
                            "venue_id": venue_id,
                            "match_date": when,
                            "status": status,
                            "toss_winner_id": teams.get(toss_w),
                            "toss_decision": toss_d or None,
                            "winner_id": teams.get(winner),
                            "victory_margin": (
                                int(margin)
                                if winner and vtype in ("runs", "wickets", "innings")
                                else None
                            ),
                            "victory_type": vtype or None,
                        }
                    ),
                    "Match added.",
                )
    elif op == "Update":
        match_id = st.number_input(
            "Match ID (see the Read tab)", min_value=1, step=1, key="m_upd_id"
        )
        current = matches.get({"match_id": int(match_id)})
        if not current:
            st.info("Enter an existing match id.")
        else:
            teams = {k: v for k, v in teams_map().items()}
            id_to_team = {v: k for k, v in teams.items()}
            with st.form("update_match"):
                desc = st.text_input("Description", value=current["match_desc"])
                status = st.selectbox(
                    "Status",
                    MATCH_STATUSES,
                    index=MATCH_STATUSES.index(current["status"]),
                )
                options = [
                    "",
                    id_to_team[current["team1_id"]],
                    id_to_team[current["team2_id"]],
                ]
                winner = st.selectbox(
                    "Winner",
                    options,
                    index=options.index(id_to_team.get(current["winner_id"], "")),
                )
                margin = st.number_input(
                    "Victory margin",
                    min_value=0,
                    max_value=1000,
                    value=int(current["victory_margin"] or 0),
                )
                vtype = st.selectbox(
                    "Victory type",
                    ["", *VICTORY_TYPES],
                    index=(
                        ["", *VICTORY_TYPES].index(current["victory_type"])
                        if current["victory_type"]
                        else 0
                    ),
                )
                result = st.selectbox(
                    "Result", RESULT_TYPES, index=RESULT_TYPES.index(current["result"])
                )
                if st.form_submit_button("Save changes", icon=":material/save:"):
                    has_margin = bool(
                        winner and vtype in ("runs", "wickets", "innings")
                    )
                    run_action(
                        lambda: matches.update(
                            {"match_id": int(match_id)},
                            {
                                "match_desc": desc,
                                "status": status,
                                "winner_id": teams.get(winner),
                                "victory_margin": int(margin) if has_margin else None,
                                "victory_type": vtype or None,
                                "result": result,
                            },
                        ),
                        "Match updated.",
                    )
    else:
        match_id = st.number_input(
            "Match ID to delete", min_value=1, step=1, key="m_del_id"
        )
        st.warning(
            "Deleting a match also deletes its innings, batting and bowling rows."
        )
        confirm = st.checkbox("I understand - delete this match", key="m_del_ok")
        if st.button("Delete match", disabled=not confirm, icon=":material/delete:"):
            run_action(
                lambda: matches.delete({"match_id": int(match_id)}), "Match deleted."
            )

# ============================================================ CAREER STATS
with tab_career:
    note(
        "Career statistics are recalculated from the match data each time you import, so manual edits are overwritten by the next import."
    )
    op = st.radio(
        "Operation", ["Read", "Create", "Update", "Delete"], horizontal=True, key="c_op"
    )
    pid = player_picker("c_player")
    if pid:
        if op == "Read":
            try:
                render_table(career.with_player_names(pid))
            except CricbuzzError as exc:
                show_error(exc)
        elif op in ("Create", "Update"):
            fmt = st.selectbox("Format", FORMATS, key="c_fmt")
            current = (
                career.get({"player_id": pid, "match_format": fmt})
                if op == "Update"
                else {}
            )
            if op == "Update" and not current:
                st.info("No career row for this player and format yet - use Create.")
            else:
                g = (
                    lambda key, default=0: (
                        current.get(key, default) if current else default
                    )
                    or default
                )  # noqa: E731
                with st.form(f"career_{op}"):
                    a, b, c = st.columns(3)
                    matches_n = a.number_input("Matches", 0, 2000, int(g("matches")))
                    innings = b.number_input("Innings", 0, 2000, int(g("innings")))
                    not_outs = c.number_input("Not outs", 0, 2000, int(g("not_outs")))
                    runs = a.number_input("Runs", 0, 100000, int(g("runs")))
                    hs = b.number_input(
                        "Highest score", 0, 600, int(g("highest_score"))
                    )
                    avg = c.number_input(
                        "Batting average", 0.0, 1000.0, float(g("batting_avg", 0.0))
                    )
                    sr = a.number_input(
                        "Strike rate", 0.0, 1000.0, float(g("strike_rate", 0.0))
                    )
                    hundreds = b.number_input("Centuries", 0, 200, int(g("centuries")))
                    fifties = c.number_input("Fifties", 0, 500, int(g("fifties")))
                    wickets = a.number_input("Wickets", 0, 2000, int(g("wickets")))
                    if st.form_submit_button("Save", icon=":material/save:"):
                        data = {
                            "matches": matches_n,
                            "innings": innings,
                            "not_outs": not_outs,
                            "runs": runs,
                            "highest_score": hs,
                            "batting_avg": avg,
                            "strike_rate": sr,
                            "centuries": hundreds,
                            "fifties": fifties,
                            "wickets": wickets,
                        }
                        if op == "Create":
                            run_action(
                                lambda: career.create(
                                    {"player_id": pid, "match_format": fmt, **data}
                                ),
                                "Career row added.",
                            )
                        else:
                            run_action(
                                lambda: career.update(
                                    {"player_id": pid, "match_format": fmt}, data
                                ),
                                "Career row updated.",
                            )
        else:
            fmt = st.selectbox("Format", FORMATS, key="c_del_fmt")
            confirm = st.checkbox(
                "I understand - delete this career row", key="c_del_ok"
            )
            if st.button(
                "Delete career row", disabled=not confirm, icon=":material/delete:"
            ):
                run_action(
                    lambda: career.delete({"player_id": pid, "match_format": fmt}),
                    "Career row deleted.",
                )

# ================================================================== VENUES
with tab_venues:
    op = st.radio(
        "Operation", ["Read / Update", "Create", "Delete"], horizontal=True, key="v_op"
    )
    if op == "Create":
        with st.form("create_venue", clear_on_submit=True):
            name = st.text_input("Venue name *")
            city = st.text_input("City *")
            country = st.text_input("Country")
            capacity = st.number_input(
                "Capacity", min_value=0, max_value=300000, value=0
            )
            if st.form_submit_button("Add venue", icon=":material/add:"):
                run_action(
                    lambda: venues_svc.create(
                        {
                            "venue_name": name,
                            "city": city,
                            "country": country,
                            "capacity": int(capacity) or None,
                        }
                    ),
                    "Venue added.",
                )
    else:
        vid = venue_picker("v_pick")
        current = venues_svc.get({"venue_id": vid}) if vid else None
        if current and op == "Read / Update":
            with st.form("update_venue"):
                name = st.text_input("Venue name", value=current["venue_name"])
                city = st.text_input("City", value=current["city"])
                country = st.text_input("Country", value=current["country"] or "")
                capacity = st.number_input(
                    "Capacity (0 = unknown)",
                    min_value=0,
                    max_value=300000,
                    value=int(current["capacity"] or 0),
                )
                if st.form_submit_button("Save changes", icon=":material/save:"):
                    run_action(
                        lambda: venues_svc.update(
                            {"venue_id": vid},
                            {
                                "venue_name": name,
                                "city": city,
                                "country": country,
                                "capacity": int(capacity) or None,
                            },
                        ),
                        "Venue updated.",
                    )
        elif current:
            st.warning("A venue that still hosts matches cannot be deleted.")
            confirm = st.checkbox("I understand - delete this venue", key="v_del_ok")
            if st.button(
                "Delete venue", disabled=not confirm, icon=":material/delete:"
            ):
                run_action(
                    lambda: venues_svc.delete({"venue_id": vid}), "Venue deleted."
                )
end_page()
