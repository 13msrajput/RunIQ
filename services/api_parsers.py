"""Pure parsing helpers that turn raw Cricbuzz API JSON into tidy Python objects.

They contain NO network or database code, which makes them trivial to unit test
and means a change in the API response shape only affects this file. Every
parser is defensive: missing keys never raise, they simply produce empty values.
"""

from __future__ import annotations

import re  # strip HTML / commentary tokens
from dataclasses import dataclass, field  # simple data containers
from datetime import datetime, timezone  # epoch conversion
from typing import Any  # type hints

import pandas as pd  # tables for the UI


# ============================== generic helpers =================================
def dig(data: Any, *keys: Any, default: Any = None) -> Any:
    """Safely walk nested dicts/lists: ``dig(d, 'a', 'b', 0)`` never raises."""
    current = data
    for key in keys:
        try:
            current = current[key]
        except (KeyError, IndexError, TypeError):
            return default
    return current if current is not None else default


def epoch_ms_to_datetime(value: Any) -> datetime | None:
    """Cricbuzz sends milliseconds since 1970 (often as a string); convert to a UTC datetime."""
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def strip_html(text: Any) -> str:
    """Remove tags and collapse whitespace."""
    clean = re.sub(r"<[^>]+>", " ", str(text or ""))
    return re.sub(r"\s+", " ", clean).strip()


def walk_dicts(payload: Any):
    """Yield every dictionary nested anywhere inside ``payload``."""
    stack = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            yield item
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


# ========================= matches ======================================
@dataclass
class LiveMatch:
    """Flat, UI-friendly view of one match."""

    match_id: int | None
    series_id: int | None
    series_name: str
    match_desc: str
    match_format: str
    state: str  # e.g. "In Progress", "Complete", "Preview"
    status: str  # sentence, e.g. "India need 23 runs"
    team1: str
    team2: str
    team1_score: str
    team2_score: str
    venue: str
    city: str
    start: datetime | None
    match_type: str = ""  # International / League / Domestic / Women
    team1_id: int | None = None
    team2_id: int | None = None
    team1_short: str = ""
    team2_short: str = ""
    venue_id: int | None = None
    is_women: bool = False


def format_score(score: Any) -> str:
    """``{'inngs1': {...}, 'inngs2': {...}}`` -> ``'187/4 (20) & 201/7 (50)'``."""
    if not isinstance(score, dict):
        return "-"
    parts: list[str] = []
    for key in sorted(score):  # inngs1, inngs2 ...
        innings = score[key]
        if not isinstance(innings, dict):
            continue
        runs, wickets, overs = (
            innings.get("runs", 0),
            innings.get("wickets"),
            innings.get("overs"),
        )
        text = (
            f"{runs}" if wickets is None else f"{runs}/{wickets}"
        )  # some payloads omit wickets
        if innings.get("isDeclared"):
            text += "d"
        if overs is not None:
            text += f" ({overs})"
        parts.append(text)
    return " & ".join(parts) if parts else "-"


def match_from_blocks(
    info: dict, score: dict, match_type: str = "", series_name: str = ""
) -> LiveMatch:
    """Build a ``LiveMatch`` from the ``matchInfo`` / ``matchScore`` dictionaries."""
    team1, team2 = dig(info, "team1", "teamName", default="Team 1"), dig(
        info, "team2", "teamName", default="Team 2"
    )
    name = dig(info, "seriesName", default=series_name)
    women = (
        match_type.lower() == "women" or "women" in f"{team1} {team2} {name}".lower()
    )
    return LiveMatch(
        match_id=dig(info, "matchId"),
        series_id=dig(info, "seriesId"),
        series_name=name,
        match_desc=dig(info, "matchDesc", default=""),
        match_format=dig(info, "matchFormat", default=""),
        state=dig(info, "state", default=""),
        status=dig(info, "status", default=""),
        team1=team1,
        team2=team2,
        team1_score=format_score(dig(score, "team1Score")),
        team2_score=format_score(dig(score, "team2Score")),
        venue=dig(info, "venueInfo", "ground", default=""),
        city=dig(info, "venueInfo", "city", default=""),
        start=epoch_ms_to_datetime(dig(info, "startDate")),
        match_type=match_type,
        team1_id=dig(info, "team1", "teamId"),
        team2_id=dig(info, "team2", "teamId"),
        team1_short=dig(info, "team1", "teamSName", default=""),
        team2_short=dig(info, "team2", "teamSName", default=""),
        venue_id=dig(info, "venueInfo", "id"),
        is_women=women,
    )


def parse_matches_response(
    payload: Any, *, only_type: str | None = None
) -> list[LiveMatch]:
    """Flatten ``typeMatches -> seriesMatches -> matches`` (live / recent / upcoming lists)."""
    results: list[LiveMatch] = []
    for type_block in dig(payload, "typeMatches", default=[]):
        match_type = dig(type_block, "matchType", default="")
        if only_type and match_type.lower() != only_type.lower():
            continue
        for series_block in dig(type_block, "seriesMatches", default=[]):
            wrapper = dig(
                series_block, "seriesAdWrapper", default={}
            )  # ad blocks have no wrapper
            for match in dig(wrapper, "matches", default=[]):
                results.append(
                    match_from_blocks(
                        dig(match, "matchInfo", default={}),
                        dig(match, "matchScore", default={}),
                        match_type,
                        dig(wrapper, "seriesName", default=""),
                    )
                )
    return results


def parse_any_matches(payload: Any) -> list[LiveMatch]:
    """Find every ``matchInfo`` block anywhere in a payload (series, team, venue and schedule responses)."""
    found: list[LiveMatch] = []
    seen: set[Any] = set()
    for item in walk_dicts(payload):
        info = item.get("matchInfo")
        if isinstance(info, dict) and info.get("matchId") not in seen:
            seen.add(info.get("matchId"))
            found.append(match_from_blocks(info, item.get("matchScore") or {}))
    return found


def parse_match_info(payload: Any) -> dict[str, Any]:
    """Header details of one match: toss, result, officials, venue and the two squads."""
    info = dig(
        payload, "matchInfo", default=payload if isinstance(payload, dict) else {}
    )
    toss = dig(info, "tossResults", default={}) or {}
    result = dig(info, "result", default={}) or {}
    venue = dig(info, "venueInfo", default=dig(payload, "venueInfo", default={})) or {}
    teams = {}
    for key in ("team1", "team2"):
        block = dig(info, key, default={}) or {}
        players = [
            {
                "Player": p.get("fullName") or p.get("name") or "",
                "Role": p.get("role", ""),
                "Captain": bool(p.get("captain")),
                "Keeper": bool(p.get("keeper")),
            }
            for p in (block.get("playerDetails") or [])
            if isinstance(p, dict)
        ]
        teams[dig(block, "name", default=dig(block, "teamName", default=key))] = players
    return {
        "description": dig(
            info, "matchDescription", default=dig(info, "matchDesc", default="")
        ),
        "format": dig(info, "matchFormat", default=""),
        "series": dig(
            info, "series", "name", default=dig(info, "seriesName", default="")
        ),
        "state": dig(info, "state", default=""),
        "status": dig(info, "status", default=""),
        "toss": (
            f"{toss.get('tossWinnerName', '')} chose to {toss.get('decision', '')}".strip()
            if toss.get("tossWinnerName")
            else ""
        ),
        "result": result.get("resultType", "") if isinstance(result, dict) else "",
        "start": epoch_ms_to_datetime(
            dig(info, "matchStartTimestamp", default=dig(info, "startDate"))
        ),
        "venue": venue.get("ground", ""),
        "city": venue.get("city", ""),
        "country": venue.get("country", ""),
        "venue_id": venue.get("id"),
        "umpires": [
            u
            for u in (
                dig(info, "umpire1", "name"),
                dig(info, "umpire2", "name"),
                dig(info, "umpire3", "name"),
            )
            if u
        ],
        "referee": dig(info, "referee", "name", default=""),
        "squads": teams,
    }


# =============================== scorecard ================================
@dataclass
class InningsScorecard:
    """One innings with batting, bowling, fall of wickets and partnerships."""

    innings_id: int
    team_name: str
    total: str
    run_rate: str = ""
    extras: str = ""
    batting: pd.DataFrame = field(default_factory=pd.DataFrame)
    bowling: pd.DataFrame = field(default_factory=pd.DataFrame)
    fow: pd.DataFrame = field(default_factory=pd.DataFrame)
    partnerships: pd.DataFrame = field(default_factory=pd.DataFrame)


def _values(block: Any) -> list[dict]:
    """``{'bat_1': {...}, 'bat_2': {...}}`` -> list of the inner dictionaries (sorted by key number)."""
    if isinstance(block, dict):
        return [
            v
            for _, v in sorted(
                block.items(), key=lambda kv: int(re.sub(r"\D", "", kv[0]) or 0)
            )
            if isinstance(v, dict)
        ]
    return [v for v in block if isinstance(v, dict)] if isinstance(block, list) else []


def parse_scorecard(payload: Any) -> list[InningsScorecard]:
    """Convert the full-scorecard response into ``InningsScorecard`` objects."""
    result: list[InningsScorecard] = []
    for innings in dig(payload, "scoreCard", default=[]):
        bat_rows = []
        for b in _values(dig(innings, "batTeamDetails", "batsmenData", default={})):
            name = (
                dig(b, "batName", default="?")
                + (" (c)" if b.get("isCaptain") else "")
                + (" (wk)" if b.get("isKeeper") else "")
            )
            bat_rows.append(
                {
                    "Batter": name,
                    "Dismissal": b.get("outDesc") or "not out",
                    "R": b.get("runs", 0),
                    "B": b.get("balls", 0),
                    "4s": b.get("fours", 0),
                    "6s": b.get("sixes", 0),
                    "SR": b.get("strikeRate", 0),
                }
            )
        bowl_rows = [
            {
                "Bowler": dig(w, "bowlName", default="?"),
                "O": w.get("overs", 0),
                "M": w.get("maidens", 0),
                "R": w.get("runs", 0),
                "W": w.get("wickets", 0),
                "Econ": w.get("economy", 0),
                "NB": w.get("no_balls", 0),
                "WD": w.get("wides", 0),
            }
            for w in _values(dig(innings, "bowlTeamDetails", "bowlersData", default={}))
        ]
        fow_rows = [
            {
                "Wkt": w.get("wktNbr"),
                "Score": w.get("wktRuns"),
                "Batter": w.get("batName", ""),
                "Over": w.get("wktOver"),
            }
            for w in _values(dig(innings, "wicketsData", default={}))
        ]
        part_rows = [
            {
                "Batter 1": f"{p.get('bat1Name', '')} {p.get('bat1Runs', '')}".strip(),
                "Batter 2": f"{p.get('bat2Name', '')} {p.get('bat2Runs', '')}".strip(),
                "Runs": p.get("totalRuns"),
                "Balls": p.get("totalBalls"),
            }
            for p in _values(dig(innings, "partnershipsData", default={}))
        ]
        sd = dig(innings, "scoreDetails", default={})
        extras = dig(innings, "extrasData", default={}) or {}
        extras_text = (
            f"{extras.get('total', 0)} (b {extras.get('byes', 0)}, lb {extras.get('legByes', 0)}, w {extras.get('wides', 0)}, nb {extras.get('noBalls', 0)}, p {extras.get('penalty', 0)})"
            if extras
            else ""
        )
        wkts = sd.get("wickets", 0)
        result.append(
            InningsScorecard(
                innings_id=dig(innings, "inningsId", default=len(result) + 1),
                team_name=dig(innings, "batTeamDetails", "batTeamName", default="Team"),
                total=f"{sd.get('runs', 0)}-{wkts} ({sd.get('overs', 0)} Ov)",
                run_rate=str(sd.get("runRate", "")),
                extras=extras_text,
                batting=pd.DataFrame(bat_rows),
                bowling=pd.DataFrame(bowl_rows),
                fow=pd.DataFrame(fow_rows),
                partnerships=pd.DataFrame(part_rows),
            )
        )
    return result


# =============================== commentary ================================
def parse_commentary(payload: Any, limit: int = 60) -> list[dict[str, Any]]:
    """Ball-by-ball commentary entries (newest first as delivered)."""
    entries: list[dict[str, Any]] = []
    for c in (
        dig(payload, "commentaryList", default=[])
        or dig(payload, "commentary", default=[])
        or []
    ):
        if not isinstance(c, dict) or not c.get("commText"):
            continue
        text = str(c["commText"])
        bold = dig(c, "commentaryFormats", "bold", default={}) or {}
        for token, value in zip(
            bold.get("formatId") or [], bold.get("formatValue") or []
        ):
            text = text.replace(
                token, str(value)
            )  # Cricbuzz stores names as B0$ placeholders
        text = re.sub(r"\bB\d+\$", "", text)
        entries.append(
            {
                "over": c.get("overNumber"),
                "event": str(c.get("event", "")).upper(),
                "text": strip_html(text),
            }
        )
        if len(entries) >= limit:
            break
    return entries


# ================================ series / teams / venues ===============================
def parse_series_list(payload: Any) -> pd.DataFrame:
    """``seriesMapProto -> series`` -> table (Month, Series, Start, End, Id)."""
    rows = []
    for month in dig(payload, "seriesMapProto", default=[]):
        for item in dig(month, "series", default=[]):
            start, end = epoch_ms_to_datetime(
                item.get("startDt")
            ), epoch_ms_to_datetime(item.get("endDt"))
            rows.append(
                {
                    "Month": dig(month, "date", default=""),
                    "Series": item.get("name", ""),
                    "Start": start.date().isoformat() if start else "",
                    "End": end.date().isoformat() if end else "",
                    "Id": item.get("id"),
                }
            )
    return pd.DataFrame(rows)


def parse_teams_list(payload: Any) -> pd.DataFrame:
    """Teams that have an id (entries without an id are group headings)."""
    rows = [
        {
            "Team": t.get("teamName", ""),
            "Short": t.get("teamSName", ""),
            "Id": t.get("teamId"),
        }
        for t in dig(payload, "list", default=[])
        if isinstance(t, dict) and t.get("teamId")
    ]
    return pd.DataFrame(rows)


def parse_team_players(payload: Any) -> pd.DataFrame:
    """Squad list; entries without an id are section headings (BATSMEN, BOWLERS ...)."""
    rows, section = [], ""
    for p in dig(payload, "player", default=[]):
        if not isinstance(p, dict):
            continue
        if not p.get("id"):
            section = p.get("name", section)
            continue
        rows.append(
            {
                "Role": section.title(),
                "Player": p.get("name", ""),
                "Batting": p.get("battingStyle", ""),
                "Bowling": p.get("bowlingStyle", ""),
                "Id": p.get("id"),
            }
        )
    return pd.DataFrame(rows)


def parse_venue(payload: Any) -> dict[str, Any]:
    """Venue details (ground, city, country, capacity, ...)."""
    if not isinstance(payload, dict):
        return {}
    keys = {
        "ground": "Ground",
        "city": "City",
        "country": "Country",
        "capacity": "Capacity",
        "established": "Established",
        "ends": "Ends",
        "floodlights": "Floodlights",
        "homeTeam": "Home team",
        "timezone": "Time zone",
        "curator": "Curator",
    }
    return {
        label: payload[key]
        for key, label in keys.items()
        if payload.get(key) not in (None, "")
    }


# ==============================stats / rankings / players =================================
def parse_rankings(payload: Any) -> pd.DataFrame:
    """``{'rank': [{...}]}`` -> DataFrame(Rank, Name, Country, Rating, Points, Trend)."""
    rows = []
    for item in dig(payload, "rank", default=[]):
        rows.append(
            {
                "Rank": pd.to_numeric(dig(item, "rank"), errors="coerce"),
                "Name": dig(item, "name", default="?"),
                "Country": dig(item, "country", default=""),
                "Rating": pd.to_numeric(dig(item, "rating"), errors="coerce"),
                "Points": pd.to_numeric(dig(item, "points"), errors="coerce"),
                "Trend": dig(item, "trend", default=""),
            }
        )
    return pd.DataFrame(rows)


def parse_table_payload(payload: Any) -> pd.DataFrame:
    """Generic ``{'headers': [...], 'values': [{'values': [...]}]}`` -> DataFrame (numbers converted)."""
    headers = dig(payload, "headers", default=[]) or []
    rows = [
        dig(item, "values", default=[])
        for item in (dig(payload, "values", default=[]) or [])
    ]
    if not rows:
        return pd.DataFrame()
    width = max(len(r) for r in rows)
    columns = list(headers) + [f"Column {i + 1}" for i in range(len(headers), width)]
    frame = pd.DataFrame(
        [r + [None] * (width - len(r)) for r in rows], columns=columns[:width]
    )
    for column in frame.columns:
        converted = pd.to_numeric(frame[column], errors="coerce")
        if converted.notna().all():
            frame[column] = converted
    return frame


def parse_player_search(payload: Any) -> pd.DataFrame:
    """Search results -> DataFrame."""
    return pd.DataFrame(
        [
            {
                "Id": p.get("id"),
                "Name": p.get("name", ""),
                "Team": p.get("teamName", ""),
                "DOB": p.get("dob", ""),
            }
            for p in dig(payload, "player", default=[])
            if isinstance(p, dict)
        ]
    )


def parse_player_info(payload: Any) -> dict[str, Any]:
    """Biography of a player."""
    if not isinstance(payload, dict):
        return {}
    fields = {
        "name": "Name",
        "nickName": "Nickname",
        "role": "Role",
        "bat": "Batting style",
        "bowl": "Bowling style",
        "intlTeam": "International team",
        "teamName": "Teams",
        "DoB": "Born",
        "birthPlace": "Birthplace",
        "height": "Height",
    }
    info = {
        label: strip_html(payload[key])
        for key, label in fields.items()
        if payload.get(key)
    }
    if payload.get("bio"):
        info["Bio"] = strip_html(payload["bio"])
    return info


# ============================== news =================================
def parse_news_list(payload: Any) -> list[dict[str, Any]]:
    """``storyList`` -> list of story dictionaries (ads are skipped)."""
    stories = []
    for entry in dig(payload, "storyList", default=[]):
        story = entry.get("story") if isinstance(entry, dict) else None
        if not story:
            continue
        published = epoch_ms_to_datetime(story.get("pubTime"))
        stories.append(
            {
                "id": story.get("id"),
                "headline": strip_html(story.get("hline")),
                "intro": strip_html(story.get("intro")),
                "source": story.get("source", ""),
                "context": story.get("context", ""),
                "published": published,
            }
        )
    return stories


def parse_news_detail(payload: Any) -> dict[str, Any]:
    """Full story: headline, intro and paragraphs."""
    paragraphs = []
    for block in dig(payload, "content", default=[]):
        inner = block.get("content") if isinstance(block, dict) else None
        if (
            isinstance(inner, dict)
            and inner.get("contentType") in (None, "Text")
            and inner.get("contentValue")
        ):
            paragraphs.append(strip_html(inner["contentValue"]))
    return {
        "headline": strip_html(
            dig(payload, "headline", default=dig(payload, "hline", default=""))
        ),
        "intro": strip_html(dig(payload, "intro", default="")),
        "paragraphs": paragraphs,
        "author": dig(payload, "authors", 0, "name", default=""),
    }
