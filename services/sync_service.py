"""Persist Cricbuzz API match data into the SQL database ("API -> SQL").

``MatchSyncService.sync`` downloads live / recent / upcoming matches and upserts
teams, venues, series and matches, then writes an audit row to ``api_sync_log``.
Running it twice never creates duplicates. A match that Cricsheet already
imported (same teams, format and date) is LINKED to the API id instead of being duplicated.
"""
from __future__ import annotations

import re  # parse "India won by 5 wkts"
from dataclasses import dataclass  # result object
from datetime import timedelta  # +/- one day when matching dates
from typing import Any

from sqlalchemy import insert, select, update  # Core statements

from api.cricbuzz_client import CricbuzzClient  # API access
from models import schema as s  # tables
from models.venue_reference import SHORT_CODES, short_code  # team codes
from services.api_parsers import LiveMatch, parse_matches_response  # parser
from utils.db_connection import get_connection  # transactions
from utils.exceptions import APIError, DatabaseError  # errors
from utils.logger import get_logger  # logging

logger = get_logger("sync")  # module logger
FORMAT_MAP = {"TEST": "Test", "ODI": "ODI", "T20": "T20I", "T20I": "T20I"}  # API value -> our value
RESULT_PATTERN = re.compile(r"^(?P<team>.+?) won by (?P<inn>an innings and )?(?P<margin>\d+) (?P<kind>runs?|wkts?|wickets?)", re.IGNORECASE)
STATE_MAP = {"complete": "Completed", "completed": "Completed", "in progress": "Live", "live": "Live", "stumps": "Live", "innings break": "Live", "preview": "Upcoming", "upcoming": "Upcoming", "toss": "Live"}


@dataclass
class SyncResult:
    """Summary returned to the UI."""

    fetched: int = 0  # matches returned by the API
    inserted: int = 0  # new rows
    updated: int = 0  # existing API rows refreshed
    linked: int = 0  # matched with an existing Cricsheet row
    skipped: int = 0  # ignored (unsupported format / league match / incomplete data)


def split_team(name: str) -> tuple[str, str]:
    """'India Women' -> ('India', 'female'); 'India' -> ('India', 'male')."""
    if name.endswith(" Women"):
        return name[: -len(" Women")], "female"
    return name, "male"


class MatchSyncService:
    """Downloads matches and stores them."""

    def __init__(self, client: CricbuzzClient | None = None) -> None:
        self.client = client or CricbuzzClient()  # injectable for tests

    def sync(self, kind: str = "recent") -> SyncResult:
        """Fetch 'recent', 'live' or 'upcoming' matches and upsert the national-team ones."""
        endpoint = f"matches/{kind}"
        fetch = {"recent": self.client.get_recent_matches, "live": self.client.get_live_matches, "upcoming": self.client.get_upcoming_matches}.get(kind)
        if fetch is None:
            raise APIError(f"Unknown match list '{kind}'.")
        try:
            matches = [m for m in parse_matches_response(fetch()) if m.match_type.lower() in ("international", "women")]
            result = self._store(matches)
        except (APIError, DatabaseError) as exc:
            self._log(endpoint, "failed", 0, exc.message)  # keep an audit trail even on failure
            raise
        self._log(endpoint, "success", result.inserted + result.updated + result.linked, f"fetched={result.fetched} skipped={result.skipped}")
        return result

    # ---------------------------------------------------------- internals
    def _store(self, matches: list[LiveMatch]) -> SyncResult:
        result = SyncResult(fetched=len(matches))
        with get_connection("saving API matches") as conn:  # all matches in ONE transaction
            for match in matches:
                fmt, start = FORMAT_MAP.get(match.match_format.upper()), match.start
                if not fmt or start is None or match.match_id is None or not (match.team1 and match.team2):
                    result.skipped += 1
                    continue
                (name1, g1), (name2, g2) = split_team(match.team1), split_team(match.team2)
                if g1 != g2 or (g1 == "female" and not (name1 in SHORT_CODES and name2 in SHORT_CODES)):
                    result.skipped += 1  # women's franchise / mixed fixtures are not national-team matches
                    continue
                gender, day = g1, start.date()
                team1, team2 = self._team_id(conn, name1, gender, match.team1_id), self._team_id(conn, name2, gender, match.team2_id)
                status = STATE_MAP.get(match.state.lower(), "Upcoming")
                winner, margin, vtype, outcome = self._parse_result(match.status, {match.team1: team1, match.team2: team2}) if status == "Completed" else (None, None, None, "normal")
                api_id = int(match.match_id)
                existing = conn.execute(select(s.matches.c.match_id).where(s.matches.c.api_match_id == api_id)).scalar()
                if existing:  # refresh an API-created row
                    conn.execute(update(s.matches).where((s.matches.c.match_id == existing) & (s.matches.c.source == "api")).values(status=status, winner_id=winner, victory_margin=margin, victory_type=vtype, result=outcome))
                    result.updated += 1
                    continue
                twin = conn.execute(select(s.matches.c.match_id).where(
                    (s.matches.c.match_format == fmt) & (s.matches.c.gender == gender) & s.matches.c.match_date.between(day - timedelta(days=1), day + timedelta(days=1))
                    & (((s.matches.c.team1_id == team1) & (s.matches.c.team2_id == team2)) | ((s.matches.c.team1_id == team2) & (s.matches.c.team2_id == team1))) & s.matches.c.api_match_id.is_(None))).scalar()
                if twin:  # Cricsheet already has it: just remember the API id
                    conn.execute(update(s.matches).where(s.matches.c.match_id == twin).values(api_match_id=api_id))
                    result.linked += 1
                    continue
                values: dict[str, Any] = dict(
                    series_id=self._series_id(conn, match, fmt, gender, day), match_desc=(match.match_desc or "Match")[:100], match_format=fmt, gender=gender, team1_id=team1, team2_id=team2,
                    venue_id=self._venue_id(conn, match.venue or "Unknown venue", match.city or "Unknown"), match_date=day, status=status, winner_id=winner, victory_margin=margin,
                    victory_type=vtype, result=outcome, match_year=day.year, match_quarter=(day.month - 1) // 3 + 1, api_match_id=api_id, source="api")
                conn.execute(insert(s.matches).values(**values))
                result.inserted += 1
        logger.info("Sync finished: %s", result)
        return result

    @staticmethod
    def _team_id(conn, name: str, gender: str, api_id: int | None) -> int:
        row = conn.execute(select(s.teams.c.team_id).where((s.teams.c.team_name == name) & (s.teams.c.gender == gender))).scalar()
        if row:
            return row
        display = name if gender == "male" else f"{name} Women"
        return conn.execute(insert(s.teams).values(team_name=name, gender=gender, display_name=display, short_name=short_code(name), country=name, api_team_id=api_id)).inserted_primary_key[0]

    @staticmethod
    def _venue_id(conn, name: str, city: str) -> int:
        row = conn.execute(select(s.venues.c.venue_id).where((s.venues.c.venue_name == name) & (s.venues.c.city == city))).scalar()
        return row or conn.execute(insert(s.venues).values(venue_name=name, city=city)).inserted_primary_key[0]

    @staticmethod
    def _series_id(conn, match: LiveMatch, fmt: str, gender: str, day) -> int | None:
        if match.series_id is None:
            return None
        row = conn.execute(select(s.series.c.series_id).where(s.series.c.api_series_id == int(match.series_id))).scalar()
        if row:
            return row
        name = (match.series_name or "Unknown series")[:200]
        row = conn.execute(select(s.series.c.series_id).where((s.series.c.series_name == name) & (s.series.c.gender == gender) & (s.series.c.match_type == fmt))).scalar()
        if row:
            return row
        return conn.execute(insert(s.series).values(series_name=name, gender=gender, match_type=fmt, start_date=day, api_series_id=int(match.series_id))).inserted_primary_key[0]

    @staticmethod
    def _parse_result(status: str, team_ids: dict[str, int]) -> tuple[int | None, int | None, str | None, str]:
        """'India won by 5 wkts' -> (team_id, 5, 'wickets', 'normal')."""
        found = RESULT_PATTERN.match(status or "")
        if found:
            winner = team_ids.get(found.group("team").strip())
            kind = "innings" if found.group("inn") else "runs" if found.group("kind").lower().startswith("run") else "wickets"
            return winner, int(found.group("margin")), kind, "normal"
        low = (status or "").lower()
        return None, None, None, "tie" if "tied" in low else "draw" if "draw" in low else "no result"

    @staticmethod
    def _log(endpoint: str, status: str, records: int, message: str) -> None:
        """Audit row; logging problems must never break the main flow."""
        try:
            with get_connection("writing the sync log") as conn:
                conn.execute(insert(s.api_sync_log).values(endpoint=endpoint, status=status, records_processed=records, message=message[:400]))
        except DatabaseError:
            logger.warning("Could not write sync log row")
