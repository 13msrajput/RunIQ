"""Streamlit helpers shared by every page (page setup, error display, data checks)."""

from __future__ import annotations

import streamlit as st  # UI library

from utils.branding import APP_NAME, logo_image  # logo + app name
from utils.db_connection import table_counts  # DB status
from utils.exceptions import (
    APIAuthError,
    APIError,
    APIRateLimitError,
    CricbuzzError,
)  # error types
from utils.logger import get_logger  # logging
from utils.theme import apply_theme, footer, render_topbar  # theme + top bar

logger = get_logger("ui")  # module logger


def setup_page(title: str, icon_symbol: str | None = None) -> None:
    """Must be the FIRST Streamlit call on every page (page config, theme, top bar)."""
    st.set_page_config(
        page_title=f"{title} | {APP_NAME}",
        page_icon=logo_image("small"),
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_theme()
    render_topbar()


def end_page() -> None:
    """Call at the very end of a page: shows the data-source attribution."""
    footer()


def show_error(exc: Exception, context: str = "") -> None:
    """Display ANY exception as a friendly message (and log the technical detail)."""
    prefix = f"{context}: " if context else ""
    if isinstance(exc, APIAuthError):
        st.error(f"{prefix}{exc.message}")
        st.info(
            "Get a key at RapidAPI (search 'Cricbuzz Cricket'), subscribe, then put it in your `.env` file as RAPIDAPI_KEY."
        )
    elif isinstance(exc, APIRateLimitError):
        st.warning(f"{prefix}{exc.message}")
    elif isinstance(exc, APIError):
        st.error(f"{prefix}{exc.message}")
        if exc.status_code == 404:
            st.caption(
                "This feature may not be included in your API plan or version. Run `python -m scripts.check_api` to see which endpoints work."
            )
    elif isinstance(exc, CricbuzzError):
        st.error(f"{prefix}{exc.message}")
    else:  # unexpected bug - never show a raw traceback to the user
        logger.exception("Unexpected error %s", context)
        st.error(
            f"{prefix}Something unexpected went wrong. Details were written to logs/app.log."
        )
    details = getattr(exc, "details", None)
    if details:
        with st.expander("Technical details"):
            st.code(str(details))


def require_data(message: str | None = None) -> bool:
    """Show a friendly 'import the data' notice (and return False) when the database is empty."""
    if table_counts().get("matches", 0) == 0:
        st.warning(
            message
            or "No match data yet. Open **Data & Settings** (More menu) and click **Import real data from Cricsheet**, or run `python -m scripts.import_cricsheet`."
        )
        return False
    return True
