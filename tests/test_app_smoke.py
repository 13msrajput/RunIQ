"""Every Streamlit page renders (dark and light) with the database only, and with a fake Cricbuzz API."""

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import config
from tests.fake_api import FakeApi

MAIN = str(
    Path(__file__).resolve().parent.parent / "main.py"
)  # AppTest resolves relative paths against the test file
PAGES = [
    "pages/1_Matches.py",
    "pages/2_Match_Centre.py",
    "pages/3_Series.py",
    "pages/4_Teams.py",
    "pages/5_Players.py",
    "pages/6_Rankings.py",
    "pages/7_Stats_and_Records.py",
    "pages/8_News.py",
    "pages/9_SQL_Analytics.py",
    "pages/10_Insights.py",
    "pages/11_Manage_Data.py",
    "pages/12_Data_and_Settings.py",
]


def problems(at):
    return [str(e.value)[:150] for e in at.exception] + [
        str(e.value)[:150] for e in at.error
    ]


def text_of(at):
    return " ".join(str(m.value) for m in at.markdown)


@pytest.fixture()
def no_api(use_seeded, monkeypatch):
    monkeypatch.setenv("RAPIDAPI_KEY", "")
    config.get_settings.cache_clear()
    st.cache_data.clear()
    yield
    config.get_settings.cache_clear()


@pytest.fixture()
def fake_api(use_seeded_copy, monkeypatch):
    monkeypatch.setenv("RAPIDAPI_KEY", "test-key-123456")
    config.get_settings.cache_clear()
    st.cache_data.clear()
    from utils import api_cache
    import api.cricbuzz_client as client_module
    import services.sync_service as sync_module

    monkeypatch.setattr(api_cache, "_client", lambda: FakeApi())
    monkeypatch.setattr(client_module, "CricbuzzClient", FakeApi)
    monkeypatch.setattr(sync_module, "CricbuzzClient", FakeApi)
    yield
    config.get_settings.cache_clear()
    st.cache_data.clear()


@pytest.mark.parametrize("light", [False, True], ids=["dark", "light"])
def test_all_pages_render_without_an_api_key(no_api, light):
    at = AppTest.from_file(MAIN, default_timeout=120)
    at.session_state["light_mode"] = light
    at.run()
    assert problems(at) == []
    assert (
        ("--bg:#e3e6e8" if light else "--bg:#1e2729") in text_of(at)
        and "RunIQ" in text_of(at)
        and "data:image/png;base64" in text_of(at)
    )
    for page in PAGES:
        at.switch_page(page).run()
        assert problems(at) == [], page


def test_theme_button_switches_between_dark_and_light(no_api):
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    assert "--bg:#1e2729" in text_of(at)
    at.button(key="theme_btn").click().run()
    assert "--bg:#e3e6e8" in text_of(at)
    at.switch_page("pages/4_Teams.py").run()
    assert "--bg:#e3e6e8" in text_of(at)  # the choice survives page changes


def test_pages_without_key_show_the_api_key_notice(no_api):
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    at.switch_page("pages/8_News.py").run()
    assert "API KEY MISSING" in text_of(at)
    at.switch_page("pages/1_Matches.py").run()
    assert "API KEY MISSING" in text_of(at)


def test_sql_analytics_runs_a_query_and_blocks_bad_sql(no_api):
    at = AppTest.from_file(MAIN, default_timeout=90).run()
    at.switch_page("pages/9_SQL_Analytics.py").run()
    at.button(key="run_prepared").click().run()
    assert "cb-table" in text_of(at) and problems(at) == []
    at.text_area[0].set_value("DROP TABLE players")
    at.button(key="run_custom").click().run()
    assert any("Only SELECT" in str(e.value) for e in at.error)


def test_pages_render_with_a_fake_api(fake_api):
    at = AppTest.from_file(MAIN, default_timeout=120).run()
    assert problems(at) == []
    assert "West Indies" in text_of(at)  # the live / recent strip shows API matches
    for page in PAGES:
        at.switch_page(page).run()
        assert problems(at) == [], page
    at.switch_page("pages/1_Matches.py").run()
    assert "WI tour of India" in text_of(at) and "118/5" in text_of(at)
    at.switch_page("pages/6_Rankings.py").run()
    assert "Abhishek Sharma" in text_of(at)
    at.switch_page("pages/8_News.py").run()
    assert "Big win for India" in text_of(at)
    at.switch_page("pages/7_Stats_and_Records.py").run()
    assert "1100" in text_of(at) or "1,100" in text_of(at)


def test_players_api_tab_and_match_centre_with_fake_api(fake_api):
    at = AppTest.from_file(MAIN, default_timeout=120).run()
    at.switch_page("pages/5_Players.py").run()
    at.text_input(key="p_api_name").set_value("kohli").run()
    assert "Virat Kohli" in text_of(at) and problems(at) == []
    at.session_state["match_ref"] = {
        "src": "api",
        "id": 1001,
        "title": "India vs West Indies",
    }
    at.switch_page("pages/2_Match_Centre.py").run()
    body = text_of(at)
    assert (
        "S Samson" in body
        and "Shamar Springer to Naman Dhir, SIX" in body
        and "M.Chinnaswamy Stadium" in body
        and problems(at) == []
    )


def test_database_match_centre_and_save_to_database(fake_api):
    from services import catalog_service as cat

    at = AppTest.from_file(MAIN, default_timeout=120).run()
    mid = int(cat.list_matches(limit=1).iloc[0]["match_id"])
    at.session_state["match_ref"] = {"src": "db", "id": mid, "title": "x"}
    at.switch_page("pages/2_Match_Centre.py").run()
    assert "cb-teambar" in text_of(at) and problems(at) == []
    at.switch_page("pages/1_Matches.py").run()
    at.button(key="save_live").click().run()
    assert any("Fetched" in str(s.value) for s in at.success), [
        str(e.value) for e in at.error
    ]


def test_manage_data_create_player_validation(no_api):
    at = AppTest.from_file(MAIN, default_timeout=90).run()
    at.switch_page("pages/11_Manage_Data.py").run()
    at.radio(key="p_op").set_value("Create").run()
    assert problems(at) == [] and any(
        "Full name" in str(w.label) for w in at.text_input
    )


def test_every_page_handles_an_empty_database(empty_db, monkeypatch):
    """First launch: no data yet. Pages must explain what to do instead of crashing."""
    monkeypatch.setenv("RAPIDAPI_KEY", "")
    config.get_settings.cache_clear()
    st.cache_data.clear()
    at = AppTest.from_file(MAIN, default_timeout=90).run()
    assert (
        problems(at) == []
        and "Data &amp; Settings" in text_of(at)
        or "Data & Settings" in text_of(at)
    )
    for page in PAGES:
        at.switch_page(page).run()
        assert [str(e.value)[:150] for e in at.exception] == [], page
    config.get_settings.cache_clear()
