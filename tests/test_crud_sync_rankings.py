"""CRUD validation, API->SQL sync and ranking snapshots against isolated databases."""

from datetime import date

import pytest

from services.career_stats_service import CareerStatsService
from services.match_service import MatchService
from services.player_service import PlayerService
from services.ranking_service import fetch_and_store, latest_snapshot
from services.sync_service import MatchSyncService, split_team
from services.venue_service import VenueService
from utils import db_connection
from utils.exceptions import RecordNotFoundError, ValidationError
from tests.test_api_parsers import MATCHES


def test_player_lifecycle_and_validation(empty_db):
    service = PlayerService()
    pk = service.create(
        {"full_name": "Test Player", "team_id": 3, "playing_role": "Batsman"}
    )
    row = service.get(pk)
    assert row["gender"] == "female"  # gender follows the team (team 3 is India Women)
    service.update(pk, {"playing_role": "Bowler", "bowling_style": "Right-arm fast"})
    assert (
        service.get(pk)["playing_role"] == "Bowler"
        and service.get(pk)["bowling_style"] == "Right-arm fast"
    )
    service.delete(pk)
    assert service.get(pk) is None
    with pytest.raises(RecordNotFoundError):
        service.delete(pk)


@pytest.mark.parametrize(
    "bad",
    [
        {"full_name": "A", "team_id": 1, "playing_role": "Batsman"},
        {"full_name": "Valid Name", "team_id": 1, "playing_role": "Wizard"},
        {"full_name": "Valid Name", "team_id": 999, "playing_role": "Batsman"},
        {
            "full_name": "Valid Name",
            "team_id": 1,
            "playing_role": "Batsman",
            "salary": 5,
        },
        {"team_id": 1, "playing_role": "Batsman"},
    ],
)
def test_player_validation_errors(empty_db, bad):
    with pytest.raises(ValidationError):
        PlayerService().create(bad)


def test_match_rules_and_derived_columns(empty_db):
    service = MatchService()
    base = {
        "match_desc": "1st ODI",
        "match_format": "ODI",
        "team1_id": 1,
        "team2_id": 2,
        "venue_id": 1,
        "match_date": date(2025, 8, 15),
    }
    pk = service.create(base)
    row = service.get(pk)
    assert (row["match_year"], row["match_quarter"], row["gender"], row["source"]) == (
        2025,
        3,
        "male",
        "manual",
    )
    with pytest.raises(ValidationError):
        service.create({**base, "team2_id": 1})  # same team twice
    with pytest.raises(ValidationError):
        service.create({**base, "team2_id": 3})  # men's team vs women's team
    with pytest.raises(ValidationError):
        service.update(
            pk, {"winner_id": 1, "victory_margin": 5, "victory_type": "runs"}
        )  # winner on an upcoming match
    service.update(
        pk,
        {
            "status": "Completed",
            "winner_id": 1,
            "victory_margin": 5,
            "victory_type": "runs",
            "match_date": date(2025, 1, 2),
        },
    )
    assert service.get(pk)["match_quarter"] == 1
    with pytest.raises(ValidationError):
        service.update(pk, {"victory_margin": None})  # a runs victory needs a margin


def test_career_stats_and_venues(empty_db):
    PlayerService().create(
        {"full_name": "Stat Player", "team_id": 1, "playing_role": "Batsman"}
    )
    service = CareerStatsService()
    pk = service.create(
        {
            "player_id": 1,
            "match_format": "ODI",
            "matches": 10,
            "innings": 9,
            "runs": 300,
        }
    )
    assert pk == {"player_id": 1, "match_format": "ODI"}
    with pytest.raises(ValidationError):
        service.create(
            {"player_id": 1, "match_format": "ODI", "matches": 1}
        )  # duplicate composite key
    with pytest.raises(ValidationError):
        service.update(pk, {"not_outs": 50})
    service.delete(pk)
    venues = VenueService()
    vpk = venues.create({"venue_name": "New Ground", "city": "Pune", "capacity": 30000})
    venues.update(vpk, {"country": "India"})
    assert venues.get(vpk)["country"] == "India"
    with pytest.raises(ValidationError):
        venues.create(
            {"venue_name": "New Ground", "city": "Pune"}
        )  # duplicate name + city
    MatchService().create(
        {
            "match_desc": "1st ODI",
            "match_format": "ODI",
            "team1_id": 1,
            "team2_id": 2,
            "venue_id": 1,
            "match_date": date(2025, 8, 15),
        }
    )
    with pytest.raises(ValidationError):
        venues.delete(
            {"venue_id": 1}
        )  # a venue that still hosts a match cannot be deleted
    venues.delete(vpk)


class FakeMatchClient:
    def __init__(self, payload=MATCHES):
        self.payload = payload

    def get_recent_matches(self):
        return self.payload

    get_live_matches = get_upcoming_matches = get_recent_matches


def test_split_team():
    assert split_team("India Women") == ("India", "female") and split_team("India") == (
        "India",
        "male",
    )


def test_sync_inserts_updates_and_skips(empty_db):
    # payload: an International T20 (India v West Indies, "No result") and a Women match (India Women v Australia Women, no format -> skipped)
    service = MatchSyncService(FakeMatchClient())
    first = service.sync("recent")
    assert (first.fetched, first.inserted, first.skipped) == (2, 1, 1)
    second = service.sync("recent")
    assert (second.inserted, second.updated) == (0, 1)  # idempotent
    row = db_connection.run_query(
        "SELECT status, result, source, api_match_id FROM matches"
    ).iloc[0]
    assert (row.status, row.result, row.source, row.api_match_id) == (
        "Completed",
        "no result",
        "api",
        1001,
    )
    assert (
        db_connection.run_query(
            "SELECT COUNT(*) AS n FROM api_sync_log WHERE status = 'success'"
        ).iloc[0, 0]
        == 2
    )


def test_sync_links_existing_cricsheet_match(empty_db):
    db_connection.set_database_url(f"sqlite:///{(empty_db / 'empty.db').as_posix()}")
    # India (1) vs "West Indies" does not exist yet; create it and a Cricsheet match on the same day
    with db_connection.get_connection() as conn:
        from sqlalchemy import text

        conn.execute(
            text(
                "INSERT INTO teams (team_name, gender, display_name, short_name, country) VALUES ('West Indies','male','West Indies','WI','West Indies')"
            )
        )
        stamp = 1760000000000 / 1000
        day = date.fromtimestamp(stamp).isoformat()
        conn.execute(
            text(
                "INSERT INTO matches (cricsheet_id, match_desc, match_format, gender, team1_id, team2_id, venue_id, match_date, status, result, dls_method, match_year, match_quarter, source) "
                f"VALUES ('c1', '5th T20I', 'T20I', 'male', 1, 4, 1, '{day}', 'Completed', 'no result', 0, 2025, 4, 'cricsheet')"
            )
        )
    result = MatchSyncService(FakeMatchClient()).sync("recent")
    assert result.linked == 1 and result.inserted == 0
    assert (
        db_connection.run_query(
            "SELECT api_match_id FROM matches WHERE cricsheet_id = 'c1'"
        ).iloc[0, 0]
        == 1001
    )


def test_sync_parses_result_sentences():
    parse = MatchSyncService._parse_result
    ids = {"India": 1, "Australia": 2}
    assert parse("India won by 5 wkts", ids) == (1, 5, "wickets", "normal")
    assert parse("Australia won by 12 runs", ids) == (2, 12, "runs", "normal")
    assert parse("India won by an innings and 25 runs", ids) == (
        1,
        25,
        "innings",
        "normal",
    )
    assert (
        parse("Match tied", ids)[3] == "tie"
        and parse("Match drawn", ids)[3] == "draw"
        and parse("Abandoned", ids)[3] == "no result"
    )


class FakeRankClient:
    def get_rankings(self, category, fmt, women):
        return {
            "rank": [
                {
                    "rank": "1",
                    "name": "A",
                    "country": "India",
                    "rating": "850",
                    "points": "9000",
                },
                {
                    "rank": "2",
                    "name": "B",
                    "country": "Australia",
                    "rating": "820",
                    "points": "8800",
                },
            ]
        }


def test_ranking_snapshot_roundtrip(empty_db):
    frame = fetch_and_store(FakeRankClient(), "batsmen", "odi", False)
    assert list(frame["Name"]) == ["A", "B"]
    stored, fetched = latest_snapshot("batsmen", "odi", False)
    assert list(stored["Name"]) == ["A", "B"] and fetched
    fetch_and_store(
        FakeRankClient(), "batsmen", "odi", False
    )  # replaces, no duplicates
    assert len(latest_snapshot("batsmen", "odi", False)[0]) == 2
    assert (
        latest_snapshot("bowlers", "odi", False)[0].empty
        and latest_snapshot("batsmen", "odi", True)[1] is None
    )
