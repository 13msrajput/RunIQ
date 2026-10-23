"""Cricsheet importer: parsing rules, integrity of the imported data, filters, idempotency and downloads."""

import pytest
import requests

from services import cricsheet_importer as ci
from services.cricsheet_importer import CricsheetImporter, parse_match
from utils import db_connection
from utils.exceptions import DataImportError


def delivery(batter, bowler, non_striker, bat=0, extras=None, wicket=None):
    d = {
        "batter": batter,
        "bowler": bowler,
        "non_striker": non_striker,
        "runs": {
            "batter": bat,
            "extras": sum((extras or {}).values()),
            "total": bat + sum((extras or {}).values()),
        },
    }
    if extras:
        d["extras"] = extras
    if wicket:
        d["wickets"] = [wicket]
    return d


def make_doc(**info):
    base = {
        "team_type": "international",
        "match_type": "T20",
        "gender": "male",
        "teams": ["India", "Australia"],
        "dates": ["2025-03-01"],
        "venue": "Eden Gardens, Kolkata",
        "city": "Kolkata",
        "outcome": {"winner": "India", "by": {"runs": 12}},
        "toss": {"winner": "India", "decision": "field"},
        "player_of_match": ["A One"],
        "overs": 20,
        "registry": {"people": {"A One": "id000001"}},
        "players": {
            "India": ["A One", "B Two", "C Three"],
            "Australia": ["X Bowl", "Y Keep", "Z Field"],
        },
        "event": {"name": "Australia tour of India", "match_number": 2},
        "season": "2025",
    }
    base.update(info)
    over0 = [
        delivery("A One", "X Bowl", "B Two", 4),
        delivery("A One", "X Bowl", "B Two", 0, {"wides": 1}),
        delivery("A One", "X Bowl", "B Two", 6),
        delivery("A One", "X Bowl", "B Two", 1),
        delivery("B Two", "X Bowl", "A One", 0, {"noballs": 1}),
        delivery(
            "B Two",
            "X Bowl",
            "A One",
            0,
            wicket={
                "player_out": "B Two",
                "kind": "caught",
                "fielders": [{"name": "Z Field"}],
            },
        ),
        delivery("C Three", "X Bowl", "A One", 1),
        delivery("A One", "X Bowl", "C Three", 2),
    ]
    over1 = [delivery("A One", "Y Keep", "C Three", 0) for _ in range(5)] + [
        delivery(
            "A One",
            "Y Keep",
            "C Three",
            0,
            wicket={
                "player_out": "A One",
                "kind": "stumped",
                "fielders": [{"name": "Y Keep"}],
            },
        )
    ]
    return {
        "info": base,
        "innings": [
            {
                "team": "India",
                "overs": [
                    {"over": 0, "deliveries": over0},
                    {"over": 1, "deliveries": over1},
                ],
            }
        ],
    }


# ------------------------------------------------------------------ pure parsing
def test_parse_counts_runs_balls_wickets_extras_and_over_data():
    inn = parse_match(make_doc(), "m1").innings[0]
    assert (inn.runs, inn.wickets, inn.balls, inn.extras) == (16, 2, 12, 2)
    assert inn.over_runs == [[16, 1], [0, 1]]
    assert inn.fow == [[1, 13, "B Two", "0.4"], [2, 16, "A One", "1.6"]]


def test_batting_order_boundaries_dismissals_and_fielding():
    inn = parse_match(make_doc(), "m1").innings[0]
    bat = {b["name"]: b for b in inn.batting}
    assert [b["name"] for b in inn.batting] == [
        "A One",
        "B Two",
        "C Three",
    ]  # order of arrival
    assert (
        bat["A One"]["runs"],
        bat["A One"]["balls"],
        bat["A One"]["fours"],
        bat["A One"]["sixes"],
    ) == (
        13,
        10,
        1,
        1,
    )  # the wide is not a ball faced
    assert (
        bat["B Two"]["balls"] == 2
        and bat["B Two"]["kind"] == "caught"
        and bat["B Two"]["fielder"] == "Z Field"
        and bat["B Two"]["bowler"] == "X Bowl"
    )
    assert bat["C Three"]["is_out"] is False and bat["A One"]["is_out"] is True
    assert (
        inn.fielding["Z Field"]["catches"] == 1
        and inn.fielding["Y Keep"]["stumpings"] == 1
    )


def test_bowling_figures_and_maidens():
    inn = parse_match(make_doc(), "m1").innings[0]
    bowl = {b["name"]: b for b in inn.bowling}
    assert (
        bowl["X Bowl"]["balls"],
        bowl["X Bowl"]["runs"],
        bowl["X Bowl"]["wickets"],
        bowl["X Bowl"]["maidens"],
        bowl["X Bowl"]["wides"],
        bowl["X Bowl"]["noballs"],
    ) == (6, 16, 1, 0, 1, 1)
    assert (
        bowl["Y Keep"]["balls"],
        bowl["Y Keep"]["runs"],
        bowl["Y Keep"]["wickets"],
        bowl["Y Keep"]["maidens"],
    ) == (6, 0, 1, 1)


def test_retired_hurt_is_not_a_dismissal_and_caught_and_bowled_credits_the_bowler():
    doc = make_doc()
    doc["innings"][0]["overs"][0]["deliveries"][-1] = delivery(
        "A One",
        "X Bowl",
        "C Three",
        0,
        wicket={"player_out": "C Three", "kind": "retired hurt"},
    )
    doc["innings"][0]["overs"][1]["deliveries"][-1] = delivery(
        "A One",
        "Y Keep",
        "C Three",
        0,
        wicket={"player_out": "A One", "kind": "caught and bowled"},
    )
    inn = parse_match(doc, "m2").innings[0]
    bat = {b["name"]: b for b in inn.batting}
    assert (
        bat["C Three"]["is_out"] is False and inn.wickets == 2
    )  # B Two (caught) + A One (c&b); retired hurt not counted
    assert inn.fielding["Y Keep"]["catches"] == 1 and bat["A One"]["fielder"] is None


@pytest.mark.parametrize(
    "outcome,expected",
    [
        ({"winner": "India", "by": {"runs": 12}}, ("India", "runs", 12, "normal")),
        (
            {"winner": "Australia", "by": {"wickets": 5}},
            ("Australia", "wickets", 5, "normal"),
        ),
        (
            {"winner": "India", "by": {"innings": 1, "runs": 80}},
            ("India", "innings", 80, "normal"),
        ),
        (
            {"result": "tie", "eliminator": "India"},
            ("India", "super_over", None, "tie"),
        ),
        ({"result": "no result"}, (None, None, None, "no result")),
        ({"result": "draw"}, (None, None, None, "draw")),
    ],
)
def test_outcome_parsing(outcome, expected):
    pm = parse_match(make_doc(outcome=outcome), "m3")
    assert (pm.winner, pm.victory_type, pm.victory_margin, pm.result) == expected


def test_toss_dls_description_and_filters():
    pm = parse_match(
        make_doc(outcome={"winner": "India", "by": {"wickets": 3}, "method": "D/L"}),
        "m4",
    )
    assert (
        pm.toss_decision == "bowl"
        and pm.dls is True
        and ci.match_description(pm) == "2nd T20I"
    )
    assert (
        pm.registry["A One"] == "id000001" and pm.fmt == "T20I" and pm.gender == "male"
    )
    assert (
        parse_match(make_doc(team_type="club"), "x") is None
    )  # leagues are not imported
    assert (
        parse_match(make_doc(match_type="IT20"), "x") is None
    )  # unofficial T20 internationals are skipped ...
    assert (
        parse_match(make_doc(match_type="IT20"), "x", include_unofficial=True).fmt
        == "T20I"
    )  # ... unless requested
    assert (
        parse_match(make_doc(match_type="MDM"), "x") is None
        and parse_match(make_doc(teams=["A"]), "x") is None
    )


def test_super_over_and_forfeited_innings_are_ignored():
    doc = make_doc()
    doc["innings"].append(
        {"team": "Australia", "super_over": True, "overs": doc["innings"][0]["overs"]}
    )
    doc["innings"].append({"team": "Australia", "forfeited": True})
    assert len(parse_match(doc, "m5").innings) == 1


def test_ordinals_and_roles():
    assert [ci._ordinal(n) for n in (1, 2, 3, 4, 11, 12, 21, 22)] == [
        "1st",
        "2nd",
        "3rd",
        "4th",
        "11th",
        "12th",
        "21st",
        "22nd",
    ]
    assert ci._derive_role(100, 5, 3.0, 20) == "Wicket-keeper"
    assert ci._derive_role(100, 80, 9.5, 0) == "Bowler"
    assert ci._derive_role(100, 40, 6.0, 0) == "All-rounder"
    assert ci._derive_role(100, 5, 3.0, 0) == "Batsman"


# ------------------------------------------------------------------ imported data (fixture database)
def test_import_summary_and_filters(use_seeded):
    q = db_connection.run_query
    assert (
        q(
            "SELECT COUNT(*) AS n FROM matches WHERE cricsheet_id IN ('900001', '900002')"
        ).iloc[0, 0]
        == 0
    )  # club + unofficial match filtered out
    kinds = q("SELECT DISTINCT match_format AS f FROM matches")["f"].tolist()
    assert set(kinds) == {"Test", "ODI", "T20I"}
    assert set(q("SELECT DISTINCT gender FROM matches")["gender"]) == {"male", "female"}


def test_team_totals_equal_batter_runs_plus_extras_and_balls_match(use_seeded):
    q = db_connection.run_query
    bad_runs = q(
        """SELECT COUNT(*) AS n FROM innings i JOIN (SELECT match_id, innings_no, SUM(runs) AS r FROM batting_performances GROUP BY match_id, innings_no) b
                    ON b.match_id = i.match_id AND b.innings_no = i.innings_no WHERE i.runs <> b.r + i.extras"""
    ).iloc[0, 0]
    bad_balls = q(
        """SELECT COUNT(*) AS n FROM innings i JOIN (SELECT match_id, innings_no, SUM(balls_bowled) AS bl, SUM(wickets) AS w FROM bowling_performances GROUP BY match_id, innings_no) b
                     ON b.match_id = i.match_id AND b.innings_no = i.innings_no WHERE i.balls <> b.bl"""
    ).iloc[0, 0]
    assert bad_runs == 0 and bad_balls == 0


def test_career_stats_match_performances_and_players_are_derived(use_seeded):
    q = db_connection.run_query
    mismatch = q(
        """SELECT COUNT(*) AS n FROM player_career_stats cs JOIN (SELECT b.player_id, m.match_format AS f, SUM(b.runs) AS r FROM batting_performances b
                    JOIN matches m ON m.match_id = b.match_id GROUP BY b.player_id, m.match_format) x ON x.player_id = cs.player_id AND x.f = cs.match_format WHERE x.r <> cs.runs"""
    ).iloc[0, 0]
    assert mismatch == 0
    assert (
        q("SELECT COUNT(*) AS n FROM player_career_stats WHERE matches < innings").iloc[
            0, 0
        ]
        == 0
    )
    roles = set(q("SELECT DISTINCT playing_role FROM players")["playing_role"])
    assert {"Batsman", "Bowler", "Wicket-keeper"} <= roles
    assert (
        q("SELECT COUNT(*) AS n FROM players WHERE last_match_date IS NULL").iloc[0, 0]
        == 0
    )


def test_venue_country_capacity_and_series_dates(use_seeded):
    q = db_connection.run_query
    venues = q("SELECT venue_name, country, capacity FROM venues").set_index(
        "venue_name"
    )
    assert (
        venues.loc["Eden Gardens", "country"] == "India"
        and venues.loc["Eden Gardens", "capacity"] == 66000
    )
    assert (
        venues.loc["Narendra Modi Stadium", "capacity"] == 132000
        and venues.loc["Lord's", "country"] == "England"
    )
    assert (
        q("SELECT COUNT(*) AS n FROM series WHERE start_date > end_date").iloc[0, 0]
        == 0
    )
    assert (
        q(
            "SELECT COUNT(*) AS n FROM series WHERE total_matches IS NULL OR total_matches < 1"
        ).iloc[0, 0]
        == 0
    )


def test_reimport_is_idempotent(use_seeded, fixture_zips):
    before = db_connection.table_counts()["matches"]
    summary = CricsheetImporter().run(zips=list(fixture_zips.values()))
    assert (
        summary.imported == 0
        and summary.skipped_existing >= before
        and db_connection.table_counts()["matches"] == before
    )


def test_importer_filters_and_limit(tmp_path, fixture_zips):
    db_connection.set_database_url(f"sqlite:///{(tmp_path / 'f.db').as_posix()}")
    db_connection.reset_database()
    summary = CricsheetImporter(formats=("T20I",), genders=("female",), limit=7).run(
        zips=list(fixture_zips.values())
    )
    assert summary.imported == 7
    assert set(
        db_connection.run_query("SELECT DISTINCT match_format AS f FROM matches")["f"]
    ) == {"T20I"}
    assert set(
        db_connection.run_query("SELECT DISTINCT gender FROM matches")["gender"]
    ) == {"female"}


def test_bad_zip_and_unready_database(tmp_path):
    db_connection.set_database_url(f"sqlite:///{(tmp_path / 'b.db').as_posix()}")
    db_connection.reset_database()
    broken = tmp_path / "broken.zip"
    broken.write_text("not a zip")
    with pytest.raises(DataImportError):
        CricsheetImporter().run(zips=[broken])


# ------------------------------------------------------------------ downloads
class _Stream:
    def __init__(self, status, chunks=()):
        self.status_code, self._chunks, self.headers = (
            status,
            chunks,
            {"content-length": str(sum(len(c) for c in chunks))},
        )

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_content(self, chunk_size):
        return iter(self._chunks)


def test_download_file_success_cache_and_errors(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        ci.requests,
        "get",
        lambda url, **kw: (calls.append(url), _Stream(200, [b"abc", b"def"]))[1],
    )
    seen = []
    path = ci.download_file(
        "https://x/y.zip", tmp_path / "y.zip", lambda d, t, m: seen.append((d, t))
    )
    assert path.read_bytes() == b"abcdef" and seen[-1] == (6, 6)
    ci.download_file("https://x/y.zip", tmp_path / "y.zip")
    assert len(calls) == 1  # second call used the cached file
    monkeypatch.setattr(ci.requests, "get", lambda url, **kw: _Stream(404))
    with pytest.raises(DataImportError, match="404"):
        ci.download_file("https://x/missing.zip", tmp_path / "missing.zip")
    monkeypatch.setattr(ci.time, "sleep", lambda s: None)

    def boom(url, **kw):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(ci.requests, "get", boom)
    with pytest.raises(DataImportError, match="Could not download"):
        ci.download_file("https://x/z.zip", tmp_path / "z.zip", retries=2)


def test_people_register_failure_is_tolerated(monkeypatch, tmp_path):
    from tests.conftest import REAL_LOAD_PEOPLE

    monkeypatch.setattr(
        ci,
        "download_file",
        lambda *a, **k: (_ for _ in ()).throw(DataImportError("offline")),
    )
    assert REAL_LOAD_PEOPLE() == {}
    csv_file = tmp_path / "people.csv"
    csv_file.write_text(
        "identifier,name,key_cricbuzz\nabc12345,V Kohli,1413\n", encoding="utf-8"
    )
    assert REAL_LOAD_PEOPLE(csv_file)["abc12345"]["key_cricbuzz"] == "1413"
