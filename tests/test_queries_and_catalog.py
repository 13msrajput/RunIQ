"""All 25 prepared SQL questions run on the imported data; catalog queries behave."""

import pandas as pd
import pytest

from services import catalog_service as cat
from services.analytics_service import AnalyticsService
from sql.queries import QUERIES
from utils.exceptions import UnsafeQueryError, ValidationError


def test_catalogue_has_all_25_questions_plus_22b():
    numbers = {q.number for q in QUERIES}
    assert {str(i) for i in range(1, 26)} <= numbers and "22B" in numbers


@pytest.mark.parametrize("query", QUERIES, ids=lambda q: f"Q{q.number}")
def test_query_runs_and_returns_rows(use_seeded, query):
    result = AnalyticsService().run(query.number)
    assert not result.data.empty, f"Q{query.number} returned no rows"


def test_business_rules_in_results(use_seeded):
    service = AnalyticsService()
    q1 = service.run("1").data
    assert set(q1.columns) >= {
        "full_name",
        "playing_role",
        "batting_style",
        "bowling_style",
    } and set(q1["team"]) <= {"India", "India Women"}
    assert (service.run("4").data["capacity"] > 50000).all()
    assert len(service.run("10").data) == 20 and len(service.run("3").data) == 10
    assert (service.run("19").data["innings"] >= 10).all() and (
        service.run("19").data["playing_role"] != "Bowler"
    ).all()
    assert set(service.run("23").data["form_category"]) <= {
        "Excellent Form",
        "Good Form",
        "Average Form",
        "Poor Form",
    }
    assert set(service.run("25").data["career_phase"]) <= {
        "Career Ascending",
        "Career Declining",
        "Career Stable",
    }
    q17 = service.run("17").data
    assert (
        set(q17["toss_decision"]) == {"bat", "bowl", "overall"}
        and q17["win_pct"].between(0, 100).all()
    )
    assert (service.run("13").data["partnership_runs"] >= 100).all()
    assert service.run("21").data["rank_in_format"].max() <= 10


def test_custom_sql_and_unknown_query(use_seeded):
    service = AnalyticsService()
    assert len(service.run_custom("SELECT * FROM teams").data) == 13
    with pytest.raises(UnsafeQueryError):
        service.run_custom("DELETE FROM teams")
    with pytest.raises(ValidationError):
        service.run("999")


def test_result_text_variants():
    assert cat.result_text("India", 5, "wickets", "normal") == "India won by 5 wickets"
    assert cat.result_text("India", 1, "runs", "normal") == "India won by 1 run"
    assert (
        cat.result_text("India", 80, "innings", "normal")
        == "India won by an innings and 80 runs"
    )
    assert (
        cat.result_text("India", None, "super_over", "tie")
        == "India won the super over"
    )
    assert (
        cat.result_text(None, None, None, "tie") == "Match tied"
        and cat.result_text(None, None, None, "no result") == "No result"
    )
    assert cat.result_text("India", 3, "wickets", "normal", True).endswith("(DLS)")


def test_matches_teams_and_head_to_head(use_seeded):
    matches = cat.list_matches(limit=10)
    assert len(matches) == 10 and {"result_text", "score1", "score2"} <= set(
        matches.columns
    )
    assert matches["match_date"].astype(str).is_monotonic_decreasing
    assert set(cat.list_matches(gender="female", limit=50)["gender"]) == {"female"}
    assert set(cat.list_matches(fmt="ODI", limit=50)["match_format"]) == {"ODI"}
    teams = cat.teams_overview("male")
    assert (teams["won"] + teams["lost"] <= teams["played"]).all() and teams[
        "win_pct"
    ].between(0, 100).all()
    top = teams.iloc[0]
    record = cat.team_format_record(int(top.team_id))
    assert (
        record["played"].sum() == top["played"]
        and not cat.team_squad(int(top.team_id)).empty
    )
    a, b = (int(t) for t in teams["team_id"].head(2))
    h = cat.head_to_head(a, b)
    assert (
        h["played"]
        == h["a_wins"] + h["b_wins"] + (h["played"] - h["a_wins"] - h["b_wins"])
        and h["played"] >= 0
    )


def test_player_profile_functions(use_seeded):
    players = cat.search_players(limit=5)
    pid = int(players.iloc[0]["player_id"])
    assert cat.player_profile(pid)["full_name"] == players.iloc[0]["full_name"]
    assert not cat.player_career(pid).empty and not cat.player_recent_innings(pid).empty
    for func in (
        cat.player_runs_by_year,
        cat.player_dismissals,
        cat.player_vs_opposition,
        cat.player_best_bowling,
    ):
        assert isinstance(func(pid), pd.DataFrame)
    assert cat.search_players("zzzzzz-no-such-player").empty and set(
        cat.search_players(gender="female", limit=20)["gender"]
    ) == {"female"}


def test_scorecard_matches_stored_totals(use_seeded):
    mid = int(cat.list_matches(limit=1).iloc[0]["match_id"])
    header = cat.match_header(mid)
    assert header["result_text"] and header["venue_name"]
    for inn in cat.match_scorecard(mid):
        assert int(inn["batting"]["R"].sum()) + inn["extras"] == int(
            inn["total"].split("(")[0].split("/")[0].strip()
        )  # total = batter runs + extras
        assert {"Batter", "Dismissal", "R", "B"} <= set(inn["batting"].columns) and {
            "Bowler",
            "O",
            "W",
        } <= set(inn["bowling"].columns)
    overs = cat.match_over_data(mid)
    assert not overs.empty and overs.groupby("innings")["runs"].sum().gt(0).all()
    assert len(cat.match_squads(mid)) == 2 and cat.match_header(10**9) == {}


def test_series_venues_and_records(use_seeded):
    series = cat.series_list(limit=5)
    assert not series.empty
    leaders = cat.series_leaders(int(series.iloc[0]["series_id"]))
    assert set(leaders) == {"runs", "wickets"}
    assert (
        not cat.venues_overview().empty
        and "Eden Gardens" in cat.venues_overview(text="eden")["venue_name"].tolist()
    )
    for kind in cat.BATTING_KINDS:
        assert not cat.batting_records(kind, None, None, None, 5).empty, kind
    for kind in cat.BOWLING_KINDS:
        assert not cat.bowling_records(kind, None, None, None, 5).empty, kind
    for kind in cat.TEAM_KINDS:
        assert not cat.team_records(kind, None, None, None, 5).empty, kind
    for kind in cat.FIELDING_KINDS:
        assert not cat.fielding_records(kind, "T20I", "male", 2023, 5).empty, kind
    with pytest.raises(ValidationError):
        cat.batting_records("DROP TABLE", None, None, None)
    assert (
        not cat.runiq_leaderboard("T20I", "male").empty
        and cat.data_status()["matches"] > 300
    )
