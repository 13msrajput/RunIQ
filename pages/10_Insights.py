"""Insights - bar, line, pie, scatter and heat-map charts built from the real match data."""

from __future__ import annotations

import plotly.express as px  # charts
import streamlit as st  # UI

from models.constants import FORMATS  # Test / ODI / T20I
from utils.db_connection import run_query  # SQL -> DataFrame
from utils.exceptions import CricbuzzError  # our errors
from utils.theme import note, page_title, section, show_chart  # UI helpers
from utils.ui_helpers import (
    end_page,
    require_data,
    setup_page,
    show_error,
)  # shared helpers

setup_page("Insights")
page_title(
    "Visual Insights",
    "Trends and comparisons drawn from every international match",
    "pie-chart",
)
if not require_data():
    end_page()
    st.stop()

c1, c2 = st.columns(2)
gender_label = c1.radio("Competition", ["Men", "Women"], horizontal=True, key="in_g")
fmt = c2.selectbox("Format", FORMATS, index=2, key="in_f")
gender = "male" if gender_label == "Men" else "female"
params = {"gender": gender, "fmt": fmt}

try:
    section("Matches per year", "calendar")
    note("Bar charts compare categories - here, how much cricket is played each year.")
    per_year = run_query(
        "SELECT match_year AS year, match_format AS format, COUNT(*) AS matches FROM matches WHERE status = 'Completed' AND gender = :gender GROUP BY match_year, match_format ORDER BY match_year",
        params,
    )
    show_chart(
        px.bar(
            per_year,
            x="year",
            y="matches",
            color="format",
            title=f"Completed {gender_label.lower()}'s matches per year",
        ),
        key="in_year",
    )

    section("Scoring trend (line chart)", "trending-up")
    note("Average first-innings total by year - are scores going up?")
    trend = run_query(
        """SELECT m.match_year AS year, ROUND(AVG(i.runs), 1) AS avg_first_innings FROM innings i JOIN matches m ON m.match_id = i.match_id
                         WHERE i.innings_no = 1 AND m.gender = :gender AND m.match_format = :fmt GROUP BY m.match_year ORDER BY m.match_year""",
        params,
    )
    trend_fig = px.line(
        trend,
        x="year",
        y="avg_first_innings",
        markers=True,
        title=f"Average first-innings score - {fmt}",
    )
    trend_fig.update_xaxes(dtick=1, tickformat="d")  # whole years only
    show_chart(trend_fig, key="in_trend")

    a, b = st.columns(2)
    with a:
        section("Toss and result (pie chart)", "target")
        toss = run_query(
            """SELECT CASE WHEN toss_winner_id = winner_id THEN 'Toss winner won' ELSE 'Toss winner lost' END AS outcome, COUNT(*) AS matches FROM matches
                            WHERE status = 'Completed' AND winner_id IS NOT NULL AND toss_winner_id IS NOT NULL AND gender = :gender AND match_format = :fmt GROUP BY outcome""",
            params,
        )
        show_chart(
            px.pie(
                toss,
                names="outcome",
                values="matches",
                title="Does winning the toss help?",
            ),
            key="in_toss",
        )
    with b:
        section("Bat first or chase (pie chart)", "zap")
        chase = run_query(
            """SELECT CASE WHEN i.team_id = m.winner_id THEN 'Batting first won' ELSE 'Chasing side won' END AS outcome, COUNT(*) AS matches
                             FROM matches m JOIN innings i ON i.match_id = m.match_id AND i.innings_no = 1 WHERE m.winner_id IS NOT NULL AND m.gender = :gender AND m.match_format = :fmt GROUP BY outcome""",
            params,
        )
        show_chart(
            px.pie(
                chase,
                names="outcome",
                values="matches",
                title="Batting first vs chasing",
            ),
            key="in_chase",
        )

    section("Team win percentage", "trophy")
    wins = run_query(
        """SELECT t.display_name AS team, COUNT(*) AS played, ROUND(100.0 * SUM(CASE WHEN m.winner_id = t.team_id THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_pct
                        FROM teams t JOIN matches m ON (m.team1_id = t.team_id OR m.team2_id = t.team_id) AND m.status = 'Completed' AND m.match_format = :fmt
                        WHERE t.gender = :gender GROUP BY t.team_id, t.display_name HAVING COUNT(*) >= 20 ORDER BY win_pct DESC LIMIT 15""",
        params,
    )
    show_chart(
        px.bar(
            wins,
            x="team",
            y="win_pct",
            hover_data=["played"],
            title=f"Win % - {fmt} (teams with 20+ matches)",
        ),
        key="in_wins",
    )

    section("Head-to-head heat-map", "layers")
    note(
        "Heat-maps make a team-vs-team matrix easy to scan. Rows = winner, columns = opponent (top teams by matches played)."
    )
    h2h = run_query(
        """SELECT w.display_name AS winner, CASE WHEN m.winner_id = m.team1_id THEN t2.display_name ELSE t1.display_name END AS opponent, COUNT(*) AS wins
                       FROM matches m JOIN teams w ON w.team_id = m.winner_id JOIN teams t1 ON t1.team_id = m.team1_id JOIN teams t2 ON t2.team_id = m.team2_id
                       WHERE m.gender = :gender AND m.match_format = :fmt GROUP BY w.display_name, opponent""",
        params,
    )
    if not h2h.empty:
        top = h2h.groupby("winner")["wins"].sum().nlargest(10).index
        matrix = (
            h2h[h2h["winner"].isin(top) & h2h["opponent"].isin(top)]
            .pivot(index="winner", columns="opponent", values="wins")
            .fillna(0)
        )
        show_chart(
            px.imshow(
                matrix,
                text_auto=True,
                aspect="auto",
                title="Wins (row team beat column team)",
            ),
            key="in_heat",
        )

    section("Batting average vs strike rate (scatter plot)", "bar-chart")
    scatter = run_query(
        """SELECT cs.player_id, p.full_name, p.playing_role AS role, cs.matches, cs.runs, cs.batting_avg, cs.strike_rate FROM player_career_stats cs JOIN players p ON p.player_id = cs.player_id
                           WHERE cs.match_format = :fmt AND p.gender = :gender AND cs.innings >= 20""",
        params,
    )
    if not scatter.empty:
        show_chart(
            px.scatter(
                scatter,
                x="strike_rate",
                y="batting_avg",
                color="role",
                size="runs",
                hover_name="full_name",
                title=f"Batting average vs strike rate - {fmt} (20+ innings)",
            ),
            key="in_scatter",
        )

    section("Player comparison", "users")
    names = run_query(
        "SELECT full_name FROM players WHERE gender = :gender ORDER BY full_name",
        params,
    )["full_name"].tolist()
    picked = st.multiselect(
        "Pick 2-4 players (type to search)", names, default=names[:2], max_selections=4
    )
    if picked:
        marks = ",".join(f":p{i}" for i in range(len(picked)))
        comp = run_query(
            f"SELECT p.full_name, p.player_id, cs.match_format, cs.runs, cs.batting_avg, cs.wickets FROM player_career_stats cs JOIN players p ON p.player_id = cs.player_id WHERE p.full_name IN ({marks})",
            {f"p{i}": n for i, n in enumerate(picked)},
        )
        metric = st.radio("Metric", ["runs", "batting_avg", "wickets"], horizontal=True)
        show_chart(
            px.bar(
                comp,
                x="match_format",
                y=metric,
                color="full_name",
                barmode="group",
                title=f"Career {metric} by format",
            ),
            key="in_compare",
        )
        note(
            "If two different players share a name they are both shown; use the Players page to tell them apart."
        )

    section("Busiest venues", "map-pin")
    venues = run_query(
        """SELECT v.venue_name, v.city, COUNT(*) AS matches, ROUND(AVG(i.runs), 1) AS avg_innings_score FROM venues v JOIN matches m ON m.venue_id = v.venue_id AND m.status = 'Completed' AND m.gender = :gender AND m.match_format = :fmt
                         JOIN innings i ON i.match_id = m.match_id GROUP BY v.venue_id, v.venue_name, v.city ORDER BY matches DESC LIMIT 15""",
        params,
    )
    show_chart(
        px.bar(
            venues,
            x="matches",
            y="venue_name",
            orientation="h",
            hover_data=["avg_innings_score"],
            title="Busiest venues",
        ),
        key="in_venues",
    )
except CricbuzzError as exc:
    show_error(exc, "Could not build the charts")
end_page()
