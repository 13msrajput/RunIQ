"""Import REAL international cricket matches from Cricsheet (cricsheet.org).

Cricsheet publishes free ball-by-ball JSON files for every Test, ODI and T20I
(men's and women's) under the Open Data Commons Attribution License (ODC-By).
This module

  1. downloads the zip files (or reads zips you downloaded yourself),
  2. parses every match into innings, batting, bowling and fielding figures,
  3. writes them to the SQL database,
  4. derives players' teams / roles / activity, venue countries and career statistics.

Parsing (`parse_match`) is a pure function, so it is easy to unit test.
"""

from __future__ import annotations

import csv  # people.csv register
import hashlib  # stable fallback ids for people without a register id
import io  # in-memory text streams
import json  # JSON parsing / storage of per-over data
import time  # measure the import duration
import zipfile  # read the Cricsheet zip archives
from collections import OrderedDict, defaultdict  # ordered batting order, counters
from dataclasses import dataclass, field  # structured results
from datetime import date, timedelta  # dates
from pathlib import Path  # file paths
from typing import Any, Callable, Iterator  # type hints

import pandas as pd  # aggregation helpers
import requests  # downloads
from sqlalchemy import delete, insert, select, text, update  # Core statements

from config import (
    CRICSHEET_DOWNLOADS,
    CRICSHEET_PEOPLE_URL,
    CRICSHEET_ZIPS,
    get_settings,
)  # URLs + settings
from models import schema as s  # table objects
from models.constants import GENDERS, RESULT_TYPES  # allowed values
from models.venue_reference import (
    infer_capacity,
    infer_country,
    short_code,
)  # static reference data
from utils.db_connection import get_connection, run_query  # DB helpers
from utils.exceptions import DataImportError, DatabaseError  # our errors
from utils.logger import get_logger  # logging

logger = get_logger("import")  # module logger
ProgressFn = Callable[[int, int, str], None]  # (done, total, message)

FORMAT_MAP = {
    "Test": "Test",
    "ODI": "ODI",
    "T20": "T20I",
}  # Cricsheet match_type -> our format (official internationals)
BOWLER_CREDIT = {
    "bowled",
    "caught",
    "caught and bowled",
    "lbw",
    "stumped",
    "hit wicket",
}  # dismissals credited to the bowler
NOT_DISMISSALS = {
    "retired hurt",
    "retired not out",
}  # batter is NOT out for these kinds
ORDINALS = {1: "1st", 2: "2nd", 3: "3rd"}  # 4th, 5th ... handled in _ordinal


def _ordinal(n: int) -> str:
    """1 -> '1st', 11 -> '11th', 22 -> '22nd'."""
    if 10 <= n % 100 <= 20:  # 11th, 12th, 13th
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


# =============================================================== parsed structures
@dataclass
class ParsedInnings:
    """One innings with batting / bowling figures."""

    innings_no: int
    team: str
    runs: int = 0
    wickets: int = 0
    balls: int = 0
    extras: int = 0
    target_runs: int | None = None
    declared: bool = False
    over_runs: list[list[int]] = field(
        default_factory=list
    )  # [[runs, wickets], ...] per over
    fow: list[list] = field(
        default_factory=list
    )  # [[wicket_no, score, player_out, over], ...]
    batting: list[dict] = field(
        default_factory=list
    )  # dicts: name, position, runs, balls, fours, sixes, is_out, kind, bowler
    bowling: list[dict] = field(
        default_factory=list
    )  # dicts: name, balls, maidens, runs, wickets, wides, noballs
    fielding: dict[str, dict[str, int]] = field(
        default_factory=dict
    )  # name -> catches / stumpings / run_outs


@dataclass
class ParsedMatch:
    """Everything needed to store one match."""

    source_id: str
    fmt: str
    gender: str
    teams: list[str]
    dates: list[date]
    venue: str
    city: str | None
    season: str | None
    event_name: str | None
    event_number: int | None
    event_stage: str | None
    match_type_number: int | None
    overs_limit: int | None
    toss_winner: str | None
    toss_decision: str | None
    winner: str | None
    victory_type: str | None
    victory_margin: int | None
    result: str
    dls: bool
    player_of_match: str | None
    squads: dict[str, list[str]]  # team -> player names
    registry: dict[str, str]  # name -> cricsheet person id
    innings: list[ParsedInnings] = field(default_factory=list)


@dataclass
class ImportSummary:
    """What happened during an import (shown in the UI)."""

    imported: int = 0
    skipped_existing: int = 0
    skipped_filtered: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0
    players_total: int = 0
    matches_total: int = 0


# =============================================================== pure parsing
def _person_id(name: str, registry: dict[str, str]) -> str:
    """Cricsheet id for ``name`` (stable hash when the register does not list the person)."""
    return registry.get(name) or "x" + hashlib.md5(name.encode("utf-8")).hexdigest()[:7]


def _parse_innings(index: int, raw: dict, bowling_team: str) -> ParsedInnings | None:
    """Convert one raw innings dictionary into batting / bowling / fielding figures."""
    if raw.get("super_over") or raw.get("forfeited") or not raw.get("overs"):
        return (
            None  # super overs and forfeited innings are not part of normal statistics
        )
    inn = ParsedInnings(
        innings_no=index, team=raw.get("team", ""), declared=bool(raw.get("declared"))
    )
    target = raw.get("target") or {}
    inn.target_runs = target.get("runs")
    penalty = raw.get("penalty_runs") or {}
    inn.runs += int(penalty.get("pre", 0)) + int(
        penalty.get("post", 0)
    )  # penalty runs count for the team
    order: "OrderedDict[str, None]" = (
        OrderedDict()
    )  # batters in order of arrival at the crease
    bat: dict[str, dict] = defaultdict(
        lambda: {
            "runs": 0,
            "balls": 0,
            "fours": 0,
            "sixes": 0,
            "is_out": False,
            "kind": None,
            "bowler": None,
            "fielder": None,
        }
    )
    bowl: dict[str, dict] = defaultdict(
        lambda: {
            "balls": 0,
            "runs": 0,
            "wickets": 0,
            "maidens": 0,
            "wides": 0,
            "noballs": 0,
        }
    )
    for over in raw["overs"]:
        over_runs = over_wkts = legal_in_over = 0  # per-over team totals
        per_bowler: dict[str, list[int]] = defaultdict(
            lambda: [0, 0]
        )  # bowler -> [runs conceded, legal balls] (for maidens)
        for d in over.get("deliveries", []):
            batter = d.get("batter") or d.get("batsman")  # older files used "batsman"
            non_striker, bowler = d.get("non_striker"), d.get("bowler")
            for person in (
                batter,
                non_striker,
            ):  # first appearance defines the batting order
                if person and person not in order:
                    order[person] = None
            runs = d.get("runs") or {}
            ex = d.get("extras") or {}
            wides, noballs = int(ex.get("wides", 0)), int(ex.get("noballs", 0))
            batter_runs, total = int(runs.get("batter", runs.get("batsman", 0))), int(
                runs.get("total", 0)
            )
            if batter:
                if wides == 0:  # a wide is not a ball faced
                    bat[batter]["balls"] += 1
                bat[batter]["runs"] += batter_runs
                if batter_runs == 4 and not runs.get("non_boundary"):
                    bat[batter]["fours"] += 1
                if batter_runs == 6 and not runs.get("non_boundary"):
                    bat[batter]["sixes"] += 1
            conceded = (
                batter_runs + wides + noballs
            )  # byes / leg-byes are not charged to the bowler
            legal = wides == 0 and noballs == 0
            if bowler:
                b = bowl[bowler]
                b["runs"] += conceded
                b["wides"] += wides
                b["noballs"] += noballs
                per_bowler[bowler][0] += conceded
                if legal:
                    b["balls"] += 1
                    per_bowler[bowler][1] += 1
            inn.runs += total
            inn.extras += int(runs.get("extras", 0))
            over_runs += total
            if legal:
                inn.balls += 1
                legal_in_over += 1
            for w in d.get("wickets") or []:  # a delivery can carry 0, 1 or 2 wickets
                out_name, kind = w.get("player_out"), w.get("kind", "")
                if out_name and kind not in NOT_DISMISSALS:
                    bat[out_name]["is_out"] = True
                    bat[out_name]["kind"] = kind
                    inn.wickets += 1
                    over_wkts += 1
                    inn.fow.append(
                        [
                            inn.wickets,
                            inn.runs,
                            out_name,
                            f"{over.get('over', 0)}.{max(legal_in_over, 1)}",
                        ]
                    )
                    if out_name not in order:
                        order[out_name] = None
                    if kind in BOWLER_CREDIT and bowler:
                        bowl[bowler]["wickets"] += 1
                        bat[out_name]["bowler"] = bowler
                    fielders = [
                        f.get("name")
                        for f in (w.get("fielders") or [])
                        if f.get("name") and not f.get("substitute")
                    ]
                    if kind == "caught and bowled" and bowler:
                        fielders = [bowler]  # the bowler took the catch
                    if kind != "caught and bowled" and fielders:
                        bat[out_name]["fielder"] = ", ".join(fielders)[
                            :100
                        ]  # shown in the scorecard as "c Fielder b Bowler"
                    credit = (
                        "catches"
                        if kind in ("caught", "caught and bowled")
                        else (
                            "stumpings"
                            if kind == "stumped"
                            else "run_outs" if kind == "run out" else None
                        )
                    )
                    if credit:
                        for name in fielders:
                            inn.fielding.setdefault(
                                name, {"catches": 0, "stumpings": 0, "run_outs": 0}
                            )[credit] += 1
                elif out_name:
                    bat[out_name]["is_out"] = False  # retired hurt: not a dismissal
        for name, (
            conceded,
            legal_balls,
        ) in per_bowler.items():  # maiden = full over of legal balls, no runs charged
            if legal_balls >= 6 and conceded == 0:
                bowl[name]["maidens"] += 1
        inn.over_runs.append([over_runs, over_wkts])
    for position, name in enumerate(order, start=1):
        b = bat[name]
        inn.batting.append(
            {
                "name": name,
                "position": position,
                "runs": b["runs"],
                "balls": b["balls"],
                "fours": b["fours"],
                "sixes": b["sixes"],
                "is_out": b["is_out"],
                "kind": b["kind"],
                "bowler": b["bowler"],
                "fielder": b["fielder"],
            }
        )
    for name, b in bowl.items():
        if b["balls"] > 0:  # the table requires at least one legal ball
            inn.bowling.append({"name": name, **b})
    return inn


def parse_match(
    data: dict, source_id: str, include_unofficial: bool = False
) -> ParsedMatch | None:
    """Convert a Cricsheet JSON document into a ``ParsedMatch`` (``None`` if it should be ignored)."""
    info = data.get("info") or {}
    if info.get("team_type") != "international":
        return None  # club / league matches are not imported
    mtype = info.get("match_type")
    fmt = FORMAT_MAP.get(mtype) or (
        "T20I" if include_unofficial and mtype == "IT20" else None
    )
    teams = info.get("teams") or []
    gender = info.get("gender", "male")
    dates = [date.fromisoformat(d) for d in (info.get("dates") or [])]
    if fmt is None or len(teams) != 2 or gender not in GENDERS or not dates:
        return None
    registry = (info.get("registry") or {}).get("people") or {}
    outcome = info.get("outcome") or {}
    by = outcome.get("by") or {}
    winner, vtype, margin = outcome.get("winner"), None, None
    if winner:
        if "innings" in by:
            vtype, margin = "innings", by.get("runs")
        elif "runs" in by:
            vtype, margin = "runs", by["runs"]
        elif "wickets" in by:
            vtype, margin = "wickets", by["wickets"]
    elif outcome.get("eliminator"):
        winner, vtype = outcome["eliminator"], "super_over"
    elif outcome.get("bowl_out"):
        winner, vtype = outcome["bowl_out"], "bowl_out"
    result = outcome.get("result") or "normal"
    result = result if result in RESULT_TYPES else "normal"
    toss = info.get("toss") or {}
    decision = {"bat": "bat", "field": "bowl"}.get(toss.get("decision"))
    event = info.get("event") or {}
    parsed = ParsedMatch(
        source_id=source_id,
        fmt=fmt,
        gender=gender,
        teams=list(teams),
        dates=dates,
        venue=(info.get("venue") or "Unknown venue").strip(),
        city=(info.get("city") or None),
        season=str(info.get("season")) if info.get("season") else None,
        event_name=event.get("name"),
        event_number=(
            event.get("match_number")
            if isinstance(event.get("match_number"), int)
            else None
        ),
        event_stage=str(event["stage"]) if event.get("stage") else None,
        match_type_number=info.get("match_type_number"),
        overs_limit=info.get("overs"),
        toss_winner=toss.get("winner"),
        toss_decision=decision if toss.get("winner") else None,
        winner=winner,
        victory_type=vtype,
        victory_margin=margin,
        result=result,
        dls=bool(outcome.get("method")),
        player_of_match=(info.get("player_of_match") or [None])[0],
        squads={t: list(p) for t, p in (info.get("players") or {}).items()},
        registry=registry,
    )
    for index, raw in enumerate(data.get("innings") or [], start=1):
        batting_team = raw.get("team", "")
        other = teams[1] if batting_team == teams[0] else teams[0]
        inn = _parse_innings(index, raw, other)
        if inn is not None:
            parsed.innings.append(inn)
    return parsed


def match_description(pm: ParsedMatch) -> str:
    """Human description such as '2nd T20I', 'Final' or 'Match 14'."""
    if pm.event_stage:
        return pm.event_stage.title()[:90]
    name = (pm.event_name or "").lower()
    if pm.event_number:
        if any(word in name for word in ("tour", "series", " in ", " v ", " vs ")):
            return f"{_ordinal(pm.event_number)} {pm.fmt}"
        return f"Match {pm.event_number}"
    return f"{pm.fmt} #{pm.match_type_number}" if pm.match_type_number else pm.fmt


# =============================================================== downloads
def download_file(
    url: str,
    dest: Path,
    progress: ProgressFn | None = None,
    *,
    refresh: bool = False,
    timeout: int = 60,
    retries: int = 3,
) -> Path:
    """Download ``url`` to ``dest`` (cached; retries on network errors)."""
    if dest.exists() and dest.stat().st_size > 0 and not refresh:
        return dest  # already downloaded
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            with requests.get(
                url,
                stream=True,
                timeout=timeout,
                headers={"User-Agent": "RunIQ/1.0 (cricket analytics project)"},
            ) as response:
                if response.status_code != 200:
                    raise DataImportError(
                        f"Download failed: HTTP {response.status_code} for {url}"
                    )
                total = int(response.headers.get("content-length", 0))
                temp = dest.with_suffix(dest.suffix + ".part")
                done = 0
                with temp.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 16):
                        handle.write(chunk)
                        done += len(chunk)
                        if progress and total:
                            progress(done, total, f"Downloading {dest.name}")
                temp.replace(dest)  # atomic: a half-finished file never looks complete
                return dest
        except DataImportError:
            raise
        except requests.RequestException as exc:  # timeouts, DNS problems, resets
            last_error = str(exc)
            logger.warning("Download attempt %d/%d failed: %s", attempt, retries, exc)
            time.sleep(1.5 * attempt)
    raise DataImportError(
        f"Could not download {url}. Check your internet connection, or download the zip manually and pass it with --zip.",
        details=last_error,
    )


def load_people_register(
    path: Path | None = None, url: str = CRICSHEET_PEOPLE_URL, *, refresh: bool = False
) -> dict[str, dict[str, str]]:
    """identifier -> {name, key_cricbuzz}. Optional: returns {} when the file is unavailable."""
    try:
        file_path = path or download_file(
            url, get_settings().data_dir / "people.csv", refresh=refresh
        )
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            return {
                row["identifier"]: {
                    "name": row.get("name", ""),
                    "key_cricbuzz": (row.get("key_cricbuzz") or "").strip(),
                }
                for row in csv.DictReader(handle)
                if row.get("identifier")
            }
    except (DataImportError, OSError, KeyError, csv.Error) as exc:
        logger.warning(
            "People register not available (%s) - continuing without Cricbuzz ids", exc
        )
        return {}


def iter_zip_matches(zip_path: Path) -> Iterator[tuple[str, dict]]:
    """Yield ``(file id, parsed JSON)`` for every .json file inside the archive."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for name in archive.namelist():
                if not name.lower().endswith(".json"):
                    continue  # README.txt etc.
                try:
                    yield Path(name).stem, json.loads(archive.read(name))
                except (json.JSONDecodeError, UnicodeDecodeError, KeyError) as exc:
                    logger.warning("Skipping unreadable file %s: %s", name, exc)
    except (zipfile.BadZipFile, OSError) as exc:
        raise DataImportError(
            f"{zip_path.name} is not a valid zip file.", details=str(exc)
        ) from exc


# =============================================================== database writer
class _Writer:
    """Inserts parsed matches, caching team / venue / player / series ids."""

    def __init__(self, conn, people: dict[str, dict[str, str]]) -> None:
        self.conn, self.people = conn, people
        self.teams = {
            (r.team_name, r.gender): r.team_id
            for r in conn.execute(
                select(s.teams.c.team_id, s.teams.c.team_name, s.teams.c.gender)
            )
        }
        self.venues = {
            (r.venue_name, r.city): r.venue_id
            for r in conn.execute(
                select(s.venues.c.venue_id, s.venues.c.venue_name, s.venues.c.city)
            )
        }
        self.players = {
            r.cricsheet_id: r.player_id
            for r in conn.execute(
                select(s.players.c.player_id, s.players.c.cricsheet_id)
            )
            if r.cricsheet_id
        }
        self.series = {
            (r.series_name, r.gender, r.match_type): r.series_id
            for r in conn.execute(
                select(
                    s.series.c.series_id,
                    s.series.c.series_name,
                    s.series.c.gender,
                    s.series.c.match_type,
                )
            )
        }
        self.batting: list[dict] = []
        self.bowling: list[dict] = []
        self.fielding: list[dict] = []
        self.squad: list[dict] = []

    def team_id(self, name: str, gender: str) -> int:
        key = (name, gender)
        if key not in self.teams:
            display = name if gender == "male" else f"{name} Women"
            self.teams[key] = self.conn.execute(
                insert(s.teams).values(
                    team_name=name,
                    gender=gender,
                    display_name=display,
                    short_name=short_code(name),
                    country=name,
                )
            ).inserted_primary_key[0]
        return self.teams[key]

    def venue_id(self, name: str, city: str | None) -> int:
        clean_name = (
            name.rsplit(", " + city, 1)[0]
            if city and name.endswith(", " + city)
            else name
        )  # "Wankhede Stadium, Mumbai" -> "Wankhede Stadium"
        key = (clean_name, city or "Unknown")
        if key not in self.venues:
            self.venues[key] = self.conn.execute(
                insert(s.venues).values(venue_name=clean_name, city=key[1])
            ).inserted_primary_key[0]
        return self.venues[key]

    def player_id(self, name: str, pm: ParsedMatch, team_id: int) -> int:
        cs_id = _person_id(name, pm.registry)
        if cs_id not in self.players:
            api_id = (self.people.get(cs_id) or {}).get("key_cricbuzz", "")
            self.players[cs_id] = self.conn.execute(
                insert(s.players).values(
                    full_name=name[:100],
                    cricsheet_id=cs_id,
                    api_player_id=int(api_id) if api_id.isdigit() else None,
                    team_id=team_id,
                    gender=pm.gender,
                    playing_role="Batsman",
                    is_active=True,
                )
            ).inserted_primary_key[0]
        return self.players[cs_id]

    def series_id(self, pm: ParsedMatch, venue_country: str | None) -> int | None:
        if not pm.event_name:
            return None
        name = (
            f"{pm.event_name}, {pm.season}"
            if pm.season and pm.season not in pm.event_name
            else pm.event_name
        )
        key = (name[:200], pm.gender, pm.fmt)
        if key not in self.series:
            self.series[key] = self.conn.execute(
                insert(s.series).values(
                    series_name=key[0],
                    season=pm.season,
                    gender=pm.gender,
                    host_country=venue_country,
                    match_type=pm.fmt,
                    start_date=pm.dates[0],
                    end_date=pm.dates[-1],
                    total_matches=1,
                )
            ).inserted_primary_key[0]
        return self.series[key]

    def write(self, pm: ParsedMatch) -> None:
        """Insert one match plus its innings and (buffered) player rows."""
        t_ids = {name: self.team_id(name, pm.gender) for name in pm.teams}
        venue_id = self.venue_id(pm.venue, pm.city)
        match_date = pm.dates[0]
        series_id = self.series_id(pm, infer_country(pm.city, pm.venue))
        pom_id = None
        status_team = pm.squads.get(pm.teams[0], [])
        match_id = self.conn.execute(
            insert(s.matches).values(
                cricsheet_id=pm.source_id,
                series_id=series_id,
                match_desc=match_description(pm),
                match_format=pm.fmt,
                gender=pm.gender,
                team1_id=t_ids[pm.teams[0]],
                team2_id=t_ids[pm.teams[1]],
                venue_id=venue_id,
                match_date=match_date,
                end_date=pm.dates[-1],
                status="Completed",
                toss_winner_id=t_ids.get(pm.toss_winner),
                toss_decision=pm.toss_decision,
                winner_id=t_ids.get(pm.winner),
                victory_margin=pm.victory_margin,
                victory_type=pm.victory_type,
                result=pm.result,
                dls_method=pm.dls,
                overs_limit=pm.overs_limit,
                match_year=match_date.year,
                match_quarter=(match_date.month - 1) // 3 + 1,
                source="cricsheet",
            )
        ).inserted_primary_key[0]
        for team, names in pm.squads.items():  # squads
            if team not in t_ids:
                continue
            for name in names:
                pid = self.player_id(name, pm, t_ids[team])
                self.squad.append(
                    {"match_id": match_id, "player_id": pid, "team_id": t_ids[team]}
                )
                if name == pm.player_of_match:
                    pom_id = pid
        if pom_id:
            self.conn.execute(
                update(s.matches)
                .where(s.matches.c.match_id == match_id)
                .values(player_of_match_id=pom_id)
            )
        for inn in pm.innings:
            bat_team = t_ids.get(inn.team)
            if bat_team is None:
                continue
            bowl_team = t_ids[pm.teams[1] if inn.team == pm.teams[0] else pm.teams[0]]
            self.conn.execute(
                insert(s.innings).values(
                    match_id=match_id,
                    innings_no=inn.innings_no,
                    team_id=bat_team,
                    runs=inn.runs,
                    wickets=inn.wickets,
                    balls=inn.balls,
                    extras=inn.extras,
                    target_runs=inn.target_runs,
                    declared=inn.declared,
                    over_runs_json=json.dumps(inn.over_runs, separators=(",", ":")),
                    fow_json=json.dumps(inn.fow, separators=(",", ":")),
                )
            )
            for b in inn.batting:
                sr = round(b["runs"] * 100 / b["balls"], 2) if b["balls"] else 0.0
                self.batting.append(
                    {
                        "match_id": match_id,
                        "innings_no": inn.innings_no,
                        "player_id": self.player_id(b["name"], pm, bat_team),
                        "team_id": bat_team,
                        "batting_position": b["position"],
                        "runs": b["runs"],
                        "balls_faced": b["balls"],
                        "fours": b["fours"],
                        "sixes": b["sixes"],
                        "strike_rate": sr,
                        "is_out": b["is_out"],
                        "dismissal_kind": b["kind"],
                        "dismissed_by_id": (
                            self.player_id(b["bowler"], pm, bowl_team)
                            if b["bowler"]
                            else None
                        ),
                        "dismissal_fielder": b["fielder"],
                    }
                )
            for b in inn.bowling:
                self.bowling.append(
                    {
                        "match_id": match_id,
                        "innings_no": inn.innings_no,
                        "player_id": self.player_id(b["name"], pm, bowl_team),
                        "team_id": bowl_team,
                        "balls_bowled": b["balls"],
                        "maidens": b["maidens"],
                        "runs_conceded": b["runs"],
                        "wickets": min(b["wickets"], 10),
                        "economy": round(b["runs"] * 6 / b["balls"], 2),
                        "wides": b["wides"],
                        "no_balls": b["noballs"],
                    }
                )
            for name, f in inn.fielding.items():
                self.fielding.append(
                    {
                        "match_id": match_id,
                        "player_id": self.player_id(name, pm, bowl_team),
                        "team_id": bowl_team,
                        **f,
                    }
                )

    def flush(self) -> None:
        """Bulk-insert the buffered child rows (fielding rows of the same match are merged first)."""
        merged: dict[tuple[int, int], dict] = {}
        for (
            row
        ) in self.fielding:  # one fielding row per (match, player) even across innings
            key = (row["match_id"], row["player_id"])
            if key in merged:
                for k in ("catches", "stumpings", "run_outs"):
                    merged[key][k] += row[k]
            else:
                merged[key] = dict(row)
        for table, rows in (
            (s.match_players, self.squad),
            (s.batting_performances, self.batting),
            (s.bowling_performances, self.bowling),
            (s.fielding_performances, list(merged.values())),
        ):
            for start in range(0, len(rows), 3000):
                self.conn.execute(insert(table), rows[start : start + 3000])
        self.squad, self.batting, self.bowling, self.fielding = [], [], [], []


# =============================================================== post-processing
def _derive_role(
    matches: int, bowled: int, avg_pos: float | None, stumpings: int
) -> str:
    """Role heuristics (Cricsheet has no role field): keeper by stumpings, bowler / all-rounder by bowling share."""
    pos = avg_pos if avg_pos is not None else 11.0
    share = bowled / matches if matches else 0.0
    if stumpings >= 3 and stumpings / max(matches, 1) >= 0.04:
        return "Wicket-keeper"
    if share >= 0.55 and pos >= 7.5:
        return "Bowler"
    if share >= 0.30 and pos <= 8.0:
        return "All-rounder"
    if share >= 0.55:
        return "Bowler"
    return "Batsman"


def rebuild_career_stats() -> int:
    """Recompute ``player_career_stats`` from the stored match data. Returns the row count."""
    base = ["player_id", "match_format"]
    app = run_query(
        "SELECT mp.player_id, m.match_format, COUNT(*) AS matches FROM match_players mp JOIN matches m ON m.match_id = mp.match_id WHERE m.status = 'Completed' GROUP BY mp.player_id, m.match_format"
    )
    bat = run_query(
        """SELECT b.player_id, m.match_format, COUNT(*) AS innings, SUM(CASE WHEN b.is_out THEN 0 ELSE 1 END) AS not_outs, SUM(b.runs) AS runs,
                              SUM(b.balls_faced) AS balls_faced, MAX(b.runs) AS highest_score, SUM(CASE WHEN b.runs >= 100 THEN 1 ELSE 0 END) AS centuries,
                              SUM(CASE WHEN b.runs >= 50 AND b.runs < 100 THEN 1 ELSE 0 END) AS fifties
                       FROM batting_performances b JOIN matches m ON m.match_id = b.match_id WHERE m.status = 'Completed' GROUP BY b.player_id, m.match_format"""
    )
    bowl = run_query(
        """SELECT bp.player_id, m.match_format, SUM(bp.wickets) AS wickets, SUM(bp.runs_conceded) AS runs_conceded, SUM(bp.balls_bowled) AS balls_bowled
                        FROM bowling_performances bp JOIN matches m ON m.match_id = bp.match_id WHERE m.status = 'Completed' GROUP BY bp.player_id, m.match_format"""
    )
    fld = run_query(
        """SELECT f.player_id, m.match_format, SUM(f.catches) AS catches, SUM(f.stumpings) AS stumpings
                       FROM fielding_performances f JOIN matches m ON m.match_id = f.match_id WHERE m.status = 'Completed' GROUP BY f.player_id, m.match_format"""
    )
    keys = pd.concat(
        [app[base], bat[base], bowl[base], fld[base]]
    ).drop_duplicates()  # every player/format that has ANY data
    df = (
        keys.merge(app, how="left", on=base)
        .merge(bat, how="left", on=base)
        .merge(bowl, how="left", on=base)
        .merge(fld, how="left", on=base)
    )
    df["matches"] = df["matches"].fillna(0)
    df["matches"] = (
        df[["matches", "innings"]].max(axis=1).fillna(df["matches"])
    )  # matches can never be fewer than innings batted
    for column in (
        "matches",
        "innings",
        "not_outs",
        "runs",
        "balls_faced",
        "highest_score",
        "centuries",
        "fifties",
        "wickets",
        "runs_conceded",
        "balls_bowled",
        "catches",
        "stumpings",
    ):
        df[column] = (
            df[column].fillna(0).astype(int)
        )  # players who never batted / bowled get zeros
    dismissals = (df["innings"] - df["not_outs"]).where(lambda x: x > 0)
    df["batting_avg"] = (df["runs"] / dismissals).round(2).fillna(0.0)
    df["strike_rate"] = (
        (100 * df["runs"] / df["balls_faced"].where(df["balls_faced"] > 0))
        .round(2)
        .fillna(0.0)
    )
    df["bowling_avg"] = (
        df["runs_conceded"] / df["wickets"].where(df["wickets"] > 0)
    ).round(2)
    df["economy"] = (
        6 * df["runs_conceded"] / df["balls_bowled"].where(df["balls_bowled"] > 0)
    ).round(2)
    columns = [
        "player_id",
        "match_format",
        "matches",
        "innings",
        "not_outs",
        "runs",
        "balls_faced",
        "highest_score",
        "batting_avg",
        "strike_rate",
        "centuries",
        "fifties",
        "wickets",
        "bowling_avg",
        "economy",
        "catches",
        "stumpings",
    ]
    records = (
        df[columns].astype(object).where(df[columns].notna(), None).to_dict("records")
    )
    with get_connection("rebuilding career statistics") as conn:
        conn.execute(delete(s.player_career_stats))
        for start in range(0, len(records), 3000):
            conn.execute(insert(s.player_career_stats), records[start : start + 3000])
    return len(records)


def finalize_import() -> None:
    """Derive players' main team / role / activity, venue countries, series dates and career stats."""
    today = date.today()
    # 1) main national team, first / last match, active flag
    teams_df = run_query(
        "SELECT mp.player_id, mp.team_id, COUNT(*) AS n FROM match_players mp GROUP BY mp.player_id, mp.team_id"
    )
    if not teams_df.empty:
        main = teams_df.sort_values(
            ["player_id", "n"], ascending=[True, False]
        ).drop_duplicates("player_id")[["player_id", "team_id"]]
        dates_df = run_query(
            "SELECT mp.player_id, MIN(m.match_date) AS first_d, MAX(m.match_date) AS last_d FROM match_players mp JOIN matches m ON m.match_id = mp.match_id GROUP BY mp.player_id"
        )
        merged = main.merge(dates_df, on="player_id")
        cutoff = (today - timedelta(days=730)).isoformat()
        rows = [
            {
                "pid": int(r.player_id),
                "tid": int(r.team_id),
                "first": r.first_d,
                "last": r.last_d,
                "active": bool(str(r.last_d) >= cutoff),
            }
            for r in merged.itertuples()
        ]
        with get_connection("updating players") as conn:
            conn.execute(
                text(
                    "UPDATE players SET team_id = :tid, first_match_date = :first, last_match_date = :last, is_active = :active WHERE player_id = :pid"
                ),
                rows,
            )
    # 2) playing role heuristics
    matches = run_query(
        "SELECT player_id, COUNT(*) AS matches FROM match_players GROUP BY player_id"
    )
    bowled = run_query(
        "SELECT player_id, COUNT(DISTINCT match_id) AS bowled FROM bowling_performances GROUP BY player_id"
    )
    pos = run_query(
        "SELECT player_id, AVG(batting_position) AS avg_pos FROM batting_performances GROUP BY player_id"
    )
    stump = run_query(
        "SELECT player_id, SUM(stumpings) AS stumpings FROM fielding_performances GROUP BY player_id"
    )
    roles = (
        matches.merge(bowled, how="left", on="player_id")
        .merge(pos, how="left", on="player_id")
        .merge(stump, how="left", on="player_id")
        .fillna({"bowled": 0, "stumpings": 0})
    )
    role_rows = [
        {
            "pid": int(r.player_id),
            "role": _derive_role(
                int(r.matches),
                int(r.bowled),
                None if pd.isna(r.avg_pos) else float(r.avg_pos),
                int(r.stumpings),
            ),
        }
        for r in roles.itertuples()
    ]
    if role_rows:
        with get_connection("updating roles") as conn:
            conn.execute(
                text("UPDATE players SET playing_role = :role WHERE player_id = :pid"),
                role_rows,
            )
    # 3) venue country + capacity
    venues_df = run_query(
        "SELECT venue_id, venue_name, city, country, capacity FROM venues"
    )
    share = run_query(
        "SELECT m.venue_id, t.country, COUNT(*) AS n FROM matches m JOIN teams t ON t.team_id IN (m.team1_id, m.team2_id) GROUP BY m.venue_id, t.country"
    )
    totals = (
        share.groupby("venue_id")["n"].sum()
        if not share.empty
        else pd.Series(dtype=float)
    )
    top = (
        share.sort_values("n", ascending=False)
        .drop_duplicates("venue_id")
        .set_index("venue_id")
        if not share.empty
        else pd.DataFrame()
    )
    venue_rows = []
    for r in venues_df.itertuples():
        country = r.country or infer_country(r.city, r.venue_name)
        if (
            not country
            and r.venue_id in top.index
            and top.loc[r.venue_id, "n"] / (totals[r.venue_id] / 2) >= 0.7
        ):
            country = top.loc[
                r.venue_id, "country"
            ]  # most matches there involve one team -> assume it is the home country
        capacity = None if pd.isna(r.capacity) else int(r.capacity)
        venue_rows.append(
            {
                "vid": int(r.venue_id),
                "country": country,
                "capacity": capacity if capacity else infer_capacity(r.venue_name),
            }
        )
    if venue_rows:
        with get_connection("updating venues") as conn:
            conn.execute(
                text(
                    "UPDATE venues SET country = :country, capacity = :capacity WHERE venue_id = :vid"
                ),
                venue_rows,
            )
    # 4) series dates, size and host country
    with get_connection("updating series") as conn:
        conn.execute(
            text(
                """UPDATE series SET
            start_date = (SELECT MIN(m.match_date) FROM matches m WHERE m.series_id = series.series_id),
            end_date = (SELECT MAX(COALESCE(m.end_date, m.match_date)) FROM matches m WHERE m.series_id = series.series_id),
            total_matches = (SELECT COUNT(*) FROM matches m WHERE m.series_id = series.series_id)
            WHERE EXISTS (SELECT 1 FROM matches m WHERE m.series_id = series.series_id)"""
            )
        )
        conn.execute(text("""UPDATE series SET host_country = (
            SELECT v.country FROM matches m JOIN venues v ON v.venue_id = m.venue_id WHERE m.series_id = series.series_id AND v.country IS NOT NULL ORDER BY m.match_date LIMIT 1)
            WHERE host_country IS NULL"""))
    # 5) career statistics
    rebuild_career_stats()


# =============================================================== orchestrator
def _batches(items: Iterator[ParsedMatch], size: int) -> Iterator[list[ParsedMatch]]:
    """Group a stream into lists of at most ``size`` items."""
    batch: list[ParsedMatch] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


class CricsheetImporter:
    """Download (or read) Cricsheet zips and load the matches into the database."""

    BATCH_SIZE = 200  # matches per database transaction

    def __init__(
        self,
        formats: tuple[str, ...] = ("Test", "ODI", "T20I"),
        genders: tuple[str, ...] = ("male", "female"),
        since_year: int | None = None,
        limit: int | None = None,
        progress: ProgressFn | None = None,
        include_unofficial: bool = False,
    ) -> None:
        self.formats, self.genders, self.since_year, self.limit = (
            formats,
            genders,
            since_year,
            limit,
        )
        self.progress, self.include_unofficial = progress, include_unofficial
        self.settings = get_settings()
        self._queued = 0  # matches handed to the writer so far (used for --limit)

    def _notify(self, done: int, total: int, message: str) -> None:
        """Forward progress to the optional callback (progress bar in the UI / CLI)."""
        if self.progress:
            self.progress(done, total, message)

    def _sources(
        self, zips: list[Path] | None, recent_days: int | None, refresh: bool
    ) -> list[Path]:
        """Local zip paths to read (downloading them first when needed)."""
        if zips:
            return [Path(z) for z in zips]
        folder = self.settings.data_dir / "cricsheet"
        if (
            recent_days
        ):  # one combined zip with every recently added match (all competitions)
            name = f"recently_added_{int(recent_days)}_json.zip"
            return [
                download_file(
                    f"{CRICSHEET_DOWNLOADS}/{name}",
                    folder / name,
                    self._notify,
                    refresh=True,
                )
            ]
        return [
            download_file(
                f"{CRICSHEET_DOWNLOADS}/{CRICSHEET_ZIPS[f]}",
                folder / CRICSHEET_ZIPS[f],
                self._notify,
                refresh=refresh,
            )
            for f in self.formats
        ]

    def _stream(
        self, zip_path: Path, existing: set[str], summary: ImportSummary
    ) -> Iterator[ParsedMatch]:
        """Parse a zip lazily, applying the user's filters and counting skipped files."""
        try:
            total_files = len(zipfile.ZipFile(zip_path).namelist())
        except (zipfile.BadZipFile, OSError) as exc:
            raise DataImportError(
                f"{zip_path.name} is not a valid zip file.", details=str(exc)
            ) from exc
        for index, (source_id, data) in enumerate(iter_zip_matches(zip_path), start=1):
            if self.limit and self._queued >= self.limit:
                return
            if index % 25 == 0:
                self._notify(
                    index,
                    total_files,
                    f"Reading {zip_path.name}: {summary.imported} matches imported",
                )
            if source_id in existing:
                summary.skipped_existing += 1
                continue
            try:
                pm = parse_match(data, source_id, self.include_unofficial)
            except (
                KeyError,
                ValueError,
                TypeError,
                AttributeError,
            ) as exc:  # one bad file must not stop the import
                summary.failed += 1
                if len(summary.errors) < 20:
                    summary.errors.append(f"{source_id}: {exc}")
                continue
            if (
                pm is None
                or pm.gender not in self.genders
                or pm.fmt not in self.formats
                or (self.since_year and pm.dates[0].year < self.since_year)
            ):
                summary.skipped_filtered += 1
                continue
            existing.add(source_id)
            self._queued += 1
            yield pm

    @staticmethod
    def _write_batch(
        batch: list[ParsedMatch], people: dict[str, dict[str, str]]
    ) -> None:
        """Write a batch in ONE transaction."""
        with get_connection("importing matches") as conn:
            writer = _Writer(conn, people)
            for pm in batch:
                writer.write(pm)
            writer.flush()

    def run(
        self,
        zips: list[Path] | None = None,
        recent_days: int | None = None,
        refresh: bool = False,
    ) -> ImportSummary:
        """Import everything; returns a summary. Raises ``DataImportError`` on fatal problems."""
        started = time.time()
        summary = ImportSummary()
        self._queued = 0
        sources = self._sources(zips, recent_days, refresh)
        people = load_people_register(refresh=refresh)
        try:
            existing = {
                r[0]
                for r in run_query(
                    "SELECT cricsheet_id FROM matches WHERE cricsheet_id IS NOT NULL"
                ).itertuples(index=False)
            }
        except DatabaseError as exc:
            raise DataImportError(
                "The database is not ready. Create the schema first.",
                details=exc.details,
            ) from exc
        for zip_path in sources:
            for batch in _batches(
                self._stream(zip_path, existing, summary), self.BATCH_SIZE
            ):
                try:
                    self._write_batch(batch, people)
                    summary.imported += len(batch)
                except (
                    DatabaseError
                ) as exc:  # retry one by one so a single odd match cannot block the others
                    logger.warning(
                        "Batch failed (%s); retrying matches individually", exc.message
                    )
                    for pm in batch:
                        try:
                            self._write_batch([pm], people)
                            summary.imported += 1
                        except DatabaseError as inner:
                            summary.failed += 1
                            if len(summary.errors) < 20:
                                summary.errors.append(
                                    f"{pm.source_id}: {inner.details or inner.message}"[
                                        :300
                                    ]
                                )
        self._notify(1, 1, "Calculating players, venues and career statistics...")
        try:
            finalize_import()
        except DatabaseError as exc:
            raise DataImportError(
                "Post-processing failed.", details=exc.details
            ) from exc
        counts = run_query(
            "SELECT (SELECT COUNT(*) FROM players) AS p, (SELECT COUNT(*) FROM matches) AS m"
        ).iloc[0]
        summary.players_total, summary.matches_total = int(counts.p), int(counts.m)
        summary.seconds = round(time.time() - started, 1)
        logger.info("Import finished: %s", summary)
        return summary
