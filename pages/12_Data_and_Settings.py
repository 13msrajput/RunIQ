"""Data & Settings - import real data, API status and tests, sync, licences."""

from __future__ import annotations

import streamlit as st  # UI

from api.cricbuzz_client import CricbuzzClient  # API access
from config import BASE_DIR, get_settings  # settings
from models.constants import FORMATS  # Test / ODI / T20I
from services import catalog_service as cat  # database queries
from services.api_probe import probe  # endpoint tests
from services.cricsheet_importer import CricsheetImporter  # importer
from services.sync_service import MatchSyncService  # API -> SQL
from utils.branding import APP_NAME, APP_VERSION  # app info
from utils.db_connection import (
    check_connection,
    create_schema,
    reset_database,
    table_counts,
)  # DB helpers
from utils.exceptions import CricbuzzError  # our errors
from utils.theme import (
    caution,
    note,
    page_title,
    render_table,
    section,
    stat_cards,
)  # UI helpers
from utils.ui_helpers import end_page, setup_page, show_error  # shared helpers

setup_page("Data & Settings")
page_title(
    "Data & Settings",
    "Import real match data, check your Cricbuzz API key and manage the database",
    "sliders",
)
settings = get_settings()
try:
    create_schema()  # makes sure the tables exist on first launch
except CricbuzzError as exc:
    show_error(exc, "Database setup")
    end_page()
    st.stop()
counts = table_counts()

# ------------------------------------------------------------------ data status
section("Data status", "database")
ok, message = check_connection()
st.caption(message if ok else f"Not connected: {message}")
if counts.get("matches", 0) == 0:
    caution(
        "The database is empty. Import the real international match history from Cricsheet below (a few minutes the first time, needs internet).",
        "FIRST STEP",
    )
else:
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
    note(f"Matches from {status['first_match']} to {status['last_match']}.")
    by_format = status["by_format"].copy()
    by_format["gender"] = by_format["gender"].map({"male": "Men", "female": "Women"})
    render_table(
        by_format.rename(
            columns={
                "match_format": "Format",
                "gender": "Competition",
                "matches": "Matches",
            }
        ),
        max_height=320,
    )

# ------------------------------------------------------------------ import
section("Import real data from Cricsheet", "download")
st.markdown(
    "Cricsheet publishes free ball-by-ball data for every Test, ODI and T20I, men's and women's. "
    "The first import downloads about 100 MB of zip files and then calculates players, venues and career statistics."
)
with st.form("import_form"):
    c1, c2, c3 = st.columns(3)
    formats = c1.multiselect("Formats", FORMATS, default=list(FORMATS))
    competitions = c2.multiselect(
        "Competitions", ["Men", "Women"], default=["Men", "Women"]
    )
    since = c3.number_input(
        "Only matches since year (0 = all history)",
        min_value=0,
        max_value=2100,
        value=0,
        step=1,
    )
    mode = st.radio(
        "What to import",
        [
            "Full history",
            "Only matches added in the last 7 days (quick update)",
            "Only matches added in the last 30 days",
        ],
        horizontal=False,
    )
    submitted = st.form_submit_button(
        "Import real data from Cricsheet", type="primary", icon=":material/download:"
    )
if submitted:
    if not formats or not competitions:
        st.error("Choose at least one format and one competition.")
    else:
        bar, text = st.progress(0.0), st.empty()

        def on_progress(done: int, total: int, msg: str) -> None:
            """Update the progress bar from the importer."""
            bar.progress(min(done / max(total, 1), 1.0))
            text.caption(msg)

        try:
            importer = CricsheetImporter(
                formats=tuple(formats),
                genders=tuple("male" if c == "Men" else "female" for c in competitions),
                since_year=int(since) or None,
                progress=on_progress,
            )
            recent = 7 if "7 days" in mode else 30 if "30 days" in mode else None
            summary = importer.run(recent_days=recent)
            st.cache_data.clear()
            st.success(
                f"Imported {summary.imported:,} new matches in {summary.seconds}s (already present: {summary.skipped_existing:,}, skipped: {summary.skipped_filtered:,}, failed: {summary.failed}). "
                f"The database now holds {summary.matches_total:,} matches and {summary.players_total:,} players."
            )
            for problem in summary.errors[:5]:
                st.caption("Problem: " + problem)
        except CricbuzzError as exc:
            show_error(exc, "Import failed")
        except Exception as exc:  # noqa: BLE001
            show_error(exc, "Unexpected import error")
note(
    "Prefer the command line? Run  python -m scripts.import_cricsheet  (add --since-year 2015 for a smaller database, or --zip file.zip to use files you downloaded yourself)."
)

# ------------------------------------------------------------------ API
section("Cricbuzz API", "zap")
c1, c2 = st.columns(2)
c1.markdown(
    f"**Key loaded:** {'yes' if settings.has_api_key else 'no'}  \n**Host:** `{settings.rapidapi_host}`  \n**.env file:** `{(BASE_DIR / '.env').exists()}`"
)
if not settings.has_api_key:
    caution(
        "Copy .env.example to .env and put your key in RAPIDAPI_KEY, then restart the app.",
        "API KEY MISSING",
    )
else:
    if c2.button(
        "Test all endpoints (about 20 API calls)", icon=":material/network_check:"
    ):
        bar, label = st.progress(0.0), st.empty()
        rows = probe(
            CricbuzzClient(),
            progress=lambda fraction, name: (
                bar.progress(min(fraction, 1.0)),
                label.caption(f"Testing {name}..."),
            ),
        )
        failed = [r for r in rows if r["Result"] not in ("OK", "SKIPPED")]
        (st.success if not failed else st.warning)(
            "All endpoints work."
            if not failed
            else f"{len(failed)} endpoint(s) failed - see the table (a 404 usually means your API version uses different paths: edit api/endpoints.py)."
        )
        import pandas as pd

        render_table(pd.DataFrame(rows))
    sync_cols = st.columns(3)
    for col, kind in zip(sync_cols, ("recent", "live", "upcoming")):
        if col.button(
            f"Save {kind} matches to database",
            key=f"sync_{kind}",
            icon=":material/sync:",
        ):
            try:
                result = MatchSyncService().sync(kind)
                st.success(
                    f"{kind.title()}: fetched {result.fetched}, new {result.inserted}, updated {result.updated}, linked to history {result.linked}, skipped {result.skipped}."
                )
                st.cache_data.clear()
            except CricbuzzError as exc:
                show_error(exc, "Sync failed")

# ------------------------------------------------------------------ danger zone
section("Danger zone", "alert")
with st.expander("Delete ALL data"):
    st.warning(
        "This empties every table (players, matches, rankings ...). You can re-import from Cricsheet afterwards."
    )
    typed = st.text_input("Type RESET to confirm", key="reset_text")
    if st.button(
        "Delete everything", disabled=typed != "RESET", icon=":material/delete_forever:"
    ):
        try:
            reset_database()
            st.cache_data.clear()
            st.success("Database emptied.")
        except CricbuzzError as exc:
            show_error(exc, "Reset failed")

# ------------------------------------------------------------------ about
section("About & licences", "info")
st.markdown(f"""
**{APP_NAME} {APP_VERSION}** - cricket scores, statistics and SQL analytics.

* **Historical data:** [Cricsheet](https://cricsheet.org) - free ball-by-ball data released under the *Open Data Commons Attribution License (ODC-By)*. Cricsheet may withhold some matches.
* **Live data:** the *Cricbuzz Cricket* API on RapidAPI, used with your own key under RapidAPI's terms.
* **Not included:** Cricbuzz website content (scores pages, photos, logos). RunIQ is independent and not affiliated with Cricbuzz, the ICC or any cricket board.
* **Derived fields:** playing roles, venue countries and stadium capacities are estimates (see the README).
""")
end_page()
