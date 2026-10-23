"""News - headlines and stories from the Cricbuzz API."""

from __future__ import annotations

import streamlit as st  # UI

from config import get_settings  # key status
from utils import api_cache  # cached API calls
from utils.theme import caution, esc, news_card, page_title, section  # UI helpers
from utils.ui_helpers import end_page, setup_page, show_error  # shared helpers

setup_page("News")
page_title("Cricket News", "Latest headlines from the Cricbuzz API", "news")
if not get_settings().has_api_key:
    caution(
        "News comes from the Cricbuzz API. Add your RAPIDAPI_KEY to the .env file to see headlines here.",
        "API KEY MISSING",
    )
    end_page()
    st.stop()
try:
    stories = api_cache.news()
except Exception as exc:  # noqa: BLE001
    show_error(exc, "Could not load the news")
    end_page()
    st.stop()
if not stories:
    st.info("No stories returned right now.")
for story in stories[:25]:
    when = (
        story["published"].strftime("%d %b %Y, %H:%M UTC")
        if story.get("published")
        else ""
    )
    news_card(
        story["headline"],
        story["intro"],
        " · ".join(
            part for part in (story.get("context"), story.get("source"), when) if part
        ),
    )
    if story.get("id") and st.button(
        "Read story", key=f"news_{story['id']}", icon=":material/article:"
    ):
        try:
            detail = api_cache.news_detail(int(story["id"]))
            section(detail.get("headline") or story["headline"], "news")
            if detail.get("intro"):
                st.markdown(f"*{detail['intro']}*")
            for paragraph in detail.get("paragraphs", []):
                st.markdown(paragraph)
            if not detail.get("paragraphs"):
                st.info("The full text is not available for this story.")
        except Exception as exc:  # noqa: BLE001
            show_error(exc, "Could not load the story")
end_page()
