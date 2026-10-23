"""SQL Analytics - the 25 questions from the project brief on REAL data, plus a guarded custom-SQL box."""

from __future__ import annotations

import plotly.express as px  # charts
import streamlit as st  # UI

from services.analytics_service import AnalyticsService  # query runner
from utils.theme import note, page_title, render_table, show_chart  # UI helpers
from utils.ui_helpers import (
    end_page,
    require_data,
    setup_page,
    show_error,
)  # shared helpers

setup_page("SQL Analytics")
page_title(
    "SQL Queries & Analytics",
    "25 prepared questions from beginner to advanced - run on the real match data",
    "database",
)
service = AnalyticsService()
if not require_data():
    end_page()
    st.stop()

tab_prepared, tab_custom = st.tabs(["Prepared questions (Q1-Q25)", "Custom SQL"])

with tab_prepared:
    level = st.radio(
        "Difficulty", ["All", "Beginner", "Intermediate", "Advanced"], horizontal=True
    )
    queries = service.list_queries(level)
    chosen = st.selectbox(
        "Question", queries, format_func=lambda q: f"[{q.level}] {q.label}"
    )
    st.markdown(f"**Business question:** {chosen.question}")
    note(f"SQL concepts: {chosen.concepts}")
    with st.expander("Show SQL", expanded=False):
        st.code(chosen.sql.strip(), language="sql")
    if st.button(
        "Run query", type="primary", key="run_prepared", icon=":material/play_arrow:"
    ):
        try:
            result = service.run(chosen.number)
        except Exception as exc:  # noqa: BLE001
            show_error(exc, "Query failed")
        else:
            st.success(f"{len(result.data):,} row(s) in {result.seconds * 1000:.1f} ms")
            render_table(result.data, empty_message="The query returned no rows.")
            if not result.data.empty:
                st.download_button(
                    "Download CSV",
                    result.data.to_csv(index=False).encode("utf-8"),
                    file_name=f"query_{chosen.number}.csv",
                    mime="text/csv",
                    icon=":material/download:",
                )
                numeric = result.data.select_dtypes("number").columns.tolist()
                text_cols = [c for c in result.data.columns if c not in numeric]
                if numeric and text_cols and len(result.data) <= 80:
                    with st.expander("Quick chart"):
                        y = st.selectbox("Value column", numeric, key="chart_y")
                        show_chart(
                            px.bar(result.data.head(25), x=text_cols[0], y=y),
                            key=f"q_chart_{chosen.number}",
                        )

with tab_custom:
    note(
        "Only a single read-only SELECT / WITH statement is allowed. Results are limited to 1000 rows."
    )
    note(
        "Tables: teams, venues, players, series, matches, innings, match_players, batting_performances, bowling_performances, fielding_performances, player_career_stats, ranking_snapshots - views: vw_match_results, vw_player_batting_summary."
    )
    sql_text = st.text_area(
        "SQL",
        height=180,
        value="SELECT display_name, short_name, gender FROM teams ORDER BY display_name",
    )
    if st.button("Run custom query", key="run_custom", icon=":material/play_arrow:"):
        try:
            result = service.run_custom(sql_text)
        except Exception as exc:  # noqa: BLE001
            show_error(exc, "Custom query failed")
        else:
            st.success(f"{len(result.data):,} row(s) in {result.seconds * 1000:.1f} ms")
            render_table(result.data)
end_page()
