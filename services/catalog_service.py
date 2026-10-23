"""Read-only data services for the RunIQ pages (teams, players, matches, series, venues, records).

Every function runs a parameterized SQL query against the real-data tables and returns a
DataFrame / dict that the pages can render directly. Nothing here writes to the database.
"""

from __future__ import annotations

import json  # per-over JSON stored on innings rows
from typing import Any

import pandas as pd  # tables

from utils.db_connection import run_query, run_scalar  # SQL helpers
from utils.exceptions import ValidationError  # bad input

# ============================================================================ helpers
MATCH_SELECT = """
    SELECT m.match_id, m.match_date, m.match_desc, m.match_format, m.gender, m.status, m.team1_id, m.team2_id, m.winner_id,
           t1.display_name AS team1, t2.display_name AS team2, w.display_name AS winner,
           m.victory_margin, m.victory_type, m.result, m.dls_method, v.venue_name, v.city, s.series_name,
           m.series_id, m.venue_id, m.toss_winner_id, m.toss_decision, pom.full_name AS player_of_match
    FROM matches m
    JOIN teams t1 ON t1.team_id = m.team1_id
    JOIN teams t2 ON t2.team_id = m.team2_id
    JOIN venues v ON v.venue_id = m.venue_id
    LEFT JOIN teams w ON w.team_id = m.winner_id
    LEFT JOIN series s ON s.series_id = m.series_id
    LEFT JOIN players pom ON pom.player_id = m.player_of_match_id
"""


def in_clause(prefix: str, values: list[Any]) -> tuple[str, dict[str, Any]]:
    """``(:p0, :p1, ...)`` plus its parameter dict, for safe ``IN`` lists."""
    names = [f"{prefix}{i}" for i in range(len(values))]
    return "(" + ", ".join(f":{n}" for n in names) + ")", dict(zip(names, values))


def result_text(
    winner: str | None,
    margin: Any,
    vtype: str | None,
    result: str | None,
    dls: bool = False,
) -> str:
    """'India won by 5 wickets', 'Match tied', ..."""
    suffix = " (DLS)" if dls else ""
    if winner:
        m = None if margin is None or pd.isna(margin) else int(margin)
        if vtype == "runs" and m is not None:
            return f"{winner} won by {m} run{'s' if m != 1 else ''}{suffix}"
        if vtype == "wickets" and m is not None:
            return f"{winner} won by {m} wicket{'s' if m != 1 else ''}{suffix}"
        if vtype == "innings":
            return f"{winner} won by an innings" + (
                f" and {m} runs" if m is not None else ""
            )
        if vtype == "super_over":
            return f"{winner} won the super over"
        if vtype == "bowl_out":
            return f"{winner} won the bowl-out"
        return f"{winner} won{suffix}"
    return {"tie": "Match tied", "no result": "No result", "draw": "Match drawn"}.get(
        result or "", "Result not available"
    )


def _score_text(rows: list[Any]) -> str:
    """'250 & 180/4' from a list of innings rows (runs, wickets, declared)."""
    parts = []
    for r in rows:
        text = (
            f"{int(r.runs)}"
            if int(r.wickets) >= 10
            else f"{int(r.runs)}/{int(r.wickets)}"
        )
        parts.append(text + ("d" if bool(r.declared) else ""))
    return " & ".join(parts)


def attach_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``result_text``, ``score1`` and ``score2`` columns to a match DataFrame."""
    if df.empty:
        return df.assign(result_text=[], score1=[], score2=[])
    df = df.copy()
    df["result_text"] = [
        result_text(
            r.winner, r.victory_margin, r.victory_type, r.result, bool(r.dls_method)
        )
        for r in df.itertuples()
    ]
    scores: dict[tuple[int, int], str] = {}
    ids = [int(i) for i in df["match_id"]]
    for start in range(0, len(ids), 800):  # keep under SQLite's parameter limit
        clause, params = in_clause("m", ids[start : start + 800])
        inn = run_query(
            f"SELECT match_id, team_id, innings_no, runs, wickets, declared FROM innings WHERE match_id IN {clause} ORDER BY match_id, innings_no",
            params,
        )
        for (mid, tid), group in inn.groupby(["match_id", "team_id"]):
            scores[(int(mid), int(tid))] = _score_text(list(group.itertuples()))
    df["score1"] = [
        scores.get((int(r.match_id), int(r.team1_id)), "") for r in df.itertuples()
    ]
    df["score2"] = [
        scores.get((int(r.match_id), int(r.team2_id)), "") for r in df.itertuples()
    ]
    return df


def matches_to_cards(df: pd.DataFrame) -> list[dict]:
    """DataFrame from ``list_matches`` -> card dictionaries for ``theme.render_strip``."""
    cards = []
    for r in df.itertuples():
        side = (
            1 if r.winner_id == r.team1_id else 2 if r.winner_id == r.team2_id else None
        )
        cards.append(
            {
                "match_id": int(r.match_id),
                "top": f"{r.match_desc} • {r.match_date}",
                "fmt": r.match_format,
                "team1": r.team1,
                "score1": r.score1,
                "team2": r.team2,
                "score2": r.score2,
                "status": r.result_text,
                "foot": f"{r.venue_name}, {r.city}",
                "winner": side,
            }
        )
    return cards


def list_matches(
    *,
    gender: str | None = None,
    fmt: str | None = None,
    team_id: int | None = None,
    year: int | None = None,
    series_id: int | None = None,
    venue_id: int | None = None,
    text: str | None = None,
    player_id: int | None = None,
    limit: int = 100,
    newest_first: bool = True,
) -> pd.DataFrame:
    """Filtered list of completed matches with result text and scores."""
    where, params = ["m.status = 'Completed'"], {"limit": int(limit)}
    if gender:
        where.append("m.gender = :gender")
        params["gender"] = gender
    if fmt:
        where.append("m.match_format = :fmt")
        params["fmt"] = fmt
    if team_id:
        where.append("(m.team1_id = :team OR m.team2_id = :team)")
        params["team"] = int(team_id)
    if year:
        where.append("m.match_year = :year")
        params["year"] = int(year)
    if series_id:
        where.append("m.series_id = :series")
        params["series"] = int(series_id)
    if venue_id:
        where.append("m.venue_id = :venue")
        params["venue"] = int(venue_id)
    if player_id:
        where.append(
            "EXISTS (SELECT 1 FROM match_players mp WHERE mp.match_id = m.match_id AND mp.player_id = :player)"
        )
        params["player"] = int(player_id)
    if text and text.strip():
        where.append(
            "(LOWER(t1.display_name) LIKE :text OR LOWER(t2.display_name) LIKE :text OR LOWER(v.venue_name) LIKE :text OR LOWER(COALESCE(s.series_name, '')) LIKE :text)"
        )
        params["text"] = f"%{text.strip().lower()}%"
    order = "DESC" if newest_first else "ASC"
    df = run_query(
        f"{MATCH_SELECT} WHERE {' AND '.join(where)} ORDER BY m.match_date {order}, m.match_id {order} LIMIT :limit",
        params,
    )
    return attach_scores(df)


def available_years() -> list[int]:
    """Years that have matches (newest first)."""
    return [
        int(y)
        for y in run_query(
            "SELECT DISTINCT match_year FROM matches WHERE status = 'Completed' ORDER BY match_year DESC"
        )["match_year"]
    ]


# ============================================================================ data status
def data_status() -> dict[str, Any]:
    """Headline numbers about the imported data (shown on Home and the Data page)."""
    row = run_query(
        """SELECT (SELECT COUNT(*) FROM matches WHERE status = 'Completed') AS matches, (SELECT COUNT(*) FROM players) AS players, (SELECT COUNT(*) FROM teams) AS teams,
                              (SELECT COUNT(*) FROM venues) AS venues, (SELECT COUNT(*) FROM series) AS series, (SELECT MIN(match_date) FROM matches) AS first_match,
                              (SELECT MAX(match_date) FROM matches WHERE status = 'Completed') AS last_match"""
    ).iloc[0]
    by = run_query(
        "SELECT match_format, gender, COUNT(*) AS matches FROM matches WHERE status = 'Completed' GROUP BY match_format, gender ORDER BY match_format, gender"
    )
    return {**{k: (None if pd.isna(v) else v) for k, v in row.items()}, "by_format": by}


# ============================================================================ teams
def teams_overview(gender: str | None = None) -> pd.DataFrame:
    """One row per team with played / won / lost / win %."""
    params: dict[str, Any] = {}
    gender_clause = ""
    if gender:
        gender_clause, params["gender"] = "WHERE t.gender = :gender", gender
    df = run_query(
        f"""
        SELECT t.team_id, t.display_name, t.team_name, t.gender, t.short_name,
               COUNT(m.match_id) AS played,
               COALESCE(SUM(CASE WHEN m.winner_id = t.team_id THEN 1 ELSE 0 END), 0) AS won,
               COALESCE(SUM(CASE WHEN m.winner_id IS NOT NULL AND m.winner_id <> t.team_id THEN 1 ELSE 0 END), 0) AS lost
        FROM teams t
        LEFT JOIN matches m ON (m.team1_id = t.team_id OR m.team2_id = t.team_id) AND m.status = 'Completed'
        {gender_clause}
        GROUP BY t.team_id, t.display_name, t.team_name, t.gender, t.short_name
        ORDER BY played DESC, t.display_name""",
        params,
    )
    df["win_pct"] = (
        (100 * df["won"] / df["played"].where(df["played"] > 0)).round(1).fillna(0.0)
    )
    return df


def team_profile(team_id: int) -> dict[str, Any]:
    """Basic details of a team."""
    df = run_query(
        "SELECT team_id, team_name, display_name, gender, short_name, country FROM teams WHERE team_id = :t",
        {"t": int(team_id)},
    )
    return {} if df.empty else df.iloc[0].to_dict()


def team_format_record(team_id: int) -> pd.DataFrame:
    """Record by format."""
    df = run_query(
        """
        SELECT m.match_format AS format, COUNT(*) AS played,
               SUM(CASE WHEN m.winner_id = :t THEN 1 ELSE 0 END) AS won,
               SUM(CASE WHEN m.winner_id IS NOT NULL AND m.winner_id <> :t THEN 1 ELSE 0 END) AS lost,
               SUM(CASE WHEN m.winner_id IS NULL THEN 1 ELSE 0 END) AS tied_nr_draw
        FROM matches m WHERE m.status = 'Completed' AND (m.team1_id = :t OR m.team2_id = :t)
        GROUP BY m.match_format ORDER BY m.match_format""",
        {"t": int(team_id)},
    )
    df["win_pct"] = (
        (100 * df["won"] / df["played"].where(df["played"] > 0)).round(1).fillna(0.0)
    )
    return df


def team_squad(team_id: int, active_only: bool = True) -> pd.DataFrame:
    """Players whose main team this is, with career totals."""
    extra = "AND p.is_active" if active_only else ""
    return run_query(
        f"""
        SELECT p.player_id, p.full_name AS player, p.playing_role AS role, p.last_match_date AS last_played,
               COALESCE(SUM(cs.matches), 0) AS matches, COALESCE(SUM(cs.runs), 0) AS runs, COALESCE(SUM(cs.wickets), 0) AS wickets
        FROM players p LEFT JOIN player_career_stats cs ON cs.player_id = p.player_id
        WHERE p.team_id = :t {extra}
        GROUP BY p.player_id, p.full_name, p.playing_role, p.last_match_date
        ORDER BY matches DESC LIMIT 60""",
        {"t": int(team_id)},
    )


def head_to_head(team_a: int, team_b: int) -> dict[str, Any]:
    """Summary, by-format table and recent meetings of two teams."""
    params = {"a": int(team_a), "b": int(team_b)}
    base = "m.status = 'Completed' AND ((m.team1_id = :a AND m.team2_id = :b) OR (m.team1_id = :b AND m.team2_id = :a))"
    by_format = run_query(
        f"""
        SELECT m.match_format AS format, COUNT(*) AS played, SUM(CASE WHEN m.winner_id = :a THEN 1 ELSE 0 END) AS a_wins,
               SUM(CASE WHEN m.winner_id = :b THEN 1 ELSE 0 END) AS b_wins, SUM(CASE WHEN m.winner_id IS NULL THEN 1 ELSE 0 END) AS no_result
        FROM matches m WHERE {base} GROUP BY m.match_format ORDER BY m.match_format""",
        params,
    )
    recent = attach_scores(
        run_query(
            f"{MATCH_SELECT} WHERE {base} ORDER BY m.match_date DESC, m.match_id DESC LIMIT 15",
            params,
        )
    )
    return {
        "by_format": by_format,
        "recent": recent,
        "played": int(by_format["played"].sum()) if not by_format.empty else 0,
        "a_wins": int(by_format["a_wins"].sum()) if not by_format.empty else 0,
        "b_wins": int(by_format["b_wins"].sum()) if not by_format.empty else 0,
    }


# ============================================================================ players
def search_players(
    text: str | None = None,
    *,
    gender: str | None = None,
    team_id: int | None = None,
    role: str | None = None,
    active_only: bool = False,
    limit: int = 200,
) -> pd.DataFrame:
    """Players with team and career totals (all formats)."""
    where, params = ["1 = 1"], {"limit": int(limit)}
    if text and text.strip():
        where.append("LOWER(p.full_name) LIKE :pattern")
        params["pattern"] = f"%{text.strip().lower()}%"
    if gender:
        where.append("p.gender = :gender")
        params["gender"] = gender
    if team_id:
        where.append("p.team_id = :team")
        params["team"] = int(team_id)
    if role:
        where.append("p.playing_role = :role")
        params["role"] = role
    if active_only:
        where.append("p.is_active")
    return run_query(
        f"""
        SELECT p.player_id, p.full_name, t.display_name AS team, p.gender, p.playing_role AS role, p.is_active,
               p.first_match_date, p.last_match_date, COALESCE(c.matches, 0) AS matches, COALESCE(c.runs, 0) AS runs, COALESCE(c.wickets, 0) AS wickets
        FROM players p JOIN teams t ON t.team_id = p.team_id
        LEFT JOIN (SELECT player_id, SUM(matches) AS matches, SUM(runs) AS runs, SUM(wickets) AS wickets FROM player_career_stats GROUP BY player_id) c ON c.player_id = p.player_id
        WHERE {' AND '.join(where)}
        ORDER BY matches DESC, p.full_name LIMIT :limit""",
        params,
    )


def player_profile(player_id: int) -> dict[str, Any]:
    df = run_query(
        """SELECT p.*, t.display_name AS team, t.team_name FROM players p JOIN teams t ON t.team_id = p.team_id WHERE p.player_id = :p""",
        {"p": int(player_id)},
    )
    return (
        {}
        if df.empty
        else {k: (None if pd.isna(v) else v) for k, v in df.iloc[0].to_dict().items()}
    )


def player_career(player_id: int) -> pd.DataFrame:
    df = run_query(
        """SELECT match_format AS format, matches, innings, not_outs, runs, highest_score AS hs, batting_avg AS avg, strike_rate AS sr, centuries AS "100s", fifties AS "50s",
                             wickets, bowling_avg AS bowl_avg, economy AS econ, catches AS ct, stumpings AS st
                      FROM player_career_stats WHERE player_id = :p ORDER BY CASE match_format WHEN 'Test' THEN 1 WHEN 'ODI' THEN 2 ELSE 3 END""",
        {"p": int(player_id)},
    )
    return df


def player_recent_innings(player_id: int, limit: int = 15) -> pd.DataFrame:
    return run_query(
        """
        SELECT m.match_date AS date, m.match_format AS format,
               CASE WHEN m.team1_id = bp.team_id THEN t2.display_name ELSE t1.display_name END AS opponent,
               bp.runs, bp.balls_faced AS balls, bp.fours AS "4s", bp.sixes AS "6s", bp.strike_rate AS sr,
               CASE WHEN bp.is_out THEN COALESCE(bp.dismissal_kind, 'out') ELSE 'not out' END AS how_out, v.venue_name AS venue
        FROM batting_performances bp JOIN matches m ON m.match_id = bp.match_id
        JOIN teams t1 ON t1.team_id = m.team1_id JOIN teams t2 ON t2.team_id = m.team2_id JOIN venues v ON v.venue_id = m.venue_id
        WHERE bp.player_id = :p ORDER BY m.match_date DESC, bp.perf_id DESC LIMIT :limit""",
        {"p": int(player_id), "limit": int(limit)},
    )


def player_runs_by_year(player_id: int) -> pd.DataFrame:
    return run_query(
        """SELECT m.match_year AS year, m.match_format AS format, COUNT(*) AS innings, SUM(bp.runs) AS runs,
                               ROUND(1.0 * SUM(bp.runs) / NULLIF(SUM(CASE WHEN bp.is_out THEN 1 ELSE 0 END), 0), 2) AS avg
                        FROM batting_performances bp JOIN matches m ON m.match_id = bp.match_id WHERE bp.player_id = :p
                        GROUP BY m.match_year, m.match_format ORDER BY m.match_year""",
        {"p": int(player_id)},
    )


def player_dismissals(player_id: int) -> pd.DataFrame:
    return run_query(
        "SELECT dismissal_kind AS how_out, COUNT(*) AS times FROM batting_performances WHERE player_id = :p AND is_out AND dismissal_kind IS NOT NULL GROUP BY dismissal_kind ORDER BY times DESC",
        {"p": int(player_id)},
    )


def player_vs_opposition(player_id: int) -> pd.DataFrame:
    return run_query(
        """
        SELECT CASE WHEN m.team1_id = bp.team_id THEN t2.display_name ELSE t1.display_name END AS opponent,
               COUNT(*) AS innings, SUM(bp.runs) AS runs, MAX(bp.runs) AS hs,
               ROUND(1.0 * SUM(bp.runs) / NULLIF(SUM(CASE WHEN bp.is_out THEN 1 ELSE 0 END), 0), 2) AS avg
        FROM batting_performances bp JOIN matches m ON m.match_id = bp.match_id
        JOIN teams t1 ON t1.team_id = m.team1_id JOIN teams t2 ON t2.team_id = m.team2_id
        WHERE bp.player_id = :p GROUP BY opponent ORDER BY runs DESC LIMIT 15""",
        {"p": int(player_id)},
    )


def player_best_bowling(player_id: int, limit: int = 8) -> pd.DataFrame:
    return run_query(
        """
        SELECT m.match_date AS date, m.match_format AS format, CASE WHEN m.team1_id = bw.team_id THEN t2.display_name ELSE t1.display_name END AS opponent,
               bw.wickets || '/' || bw.runs_conceded AS figures, ROUND(bw.balls_bowled / 6.0, 1) AS overs, bw.economy AS econ
        FROM bowling_performances bw JOIN matches m ON m.match_id = bw.match_id JOIN teams t1 ON t1.team_id = m.team1_id JOIN teams t2 ON t2.team_id = m.team2_id
        WHERE bw.player_id = :p ORDER BY bw.wickets DESC, bw.runs_conceded ASC LIMIT :limit""",
        {"p": int(player_id), "limit": int(limit)},
    )


# ============================================================================ match centre (database matches)
def match_header(match_id: int) -> dict[str, Any]:
    df = attach_scores(
        run_query(f"{MATCH_SELECT} WHERE m.match_id = :m", {"m": int(match_id)})
    )
    if df.empty:
        return {}
    row = {k: (None if pd.isna(v) else v) for k, v in df.iloc[0].to_dict().items()}
    toss_team = (
        run_scalar(
            "SELECT display_name FROM teams WHERE team_id = :t",
            {"t": row.get("toss_winner_id")},
        )
        if row.get("toss_winner_id")
        else None
    )
    row["toss_text"] = (
        f"{toss_team} chose to {row['toss_decision']}"
        if toss_team and row.get("toss_decision")
        else ""
    )
    return row


def _overs_text(balls: int) -> str:
    return f"{balls // 6}.{balls % 6}"


def _dismissal_text(
    kind: str | None, is_out: bool, bowler: str | None, fielder: str | None = None
) -> str:
    """Scorecard wording: 'c Fielder b Bowler', 'lbw b Bowler', 'run out (Fielder)' ..."""
    if not is_out:
        return "not out"
    k = (kind or "out").lower()
    b = f" b {bowler}" if bowler else ""
    f = f" {fielder}" if fielder else ""
    return {
        "bowled": f"b {bowler}" if bowler else "bowled",
        "lbw": f"lbw{b}",
        "caught": f"c{f}{b}" if (bowler or fielder) else "caught",
        "caught and bowled": f"c & b {bowler}" if bowler else "c & b",
        "stumped": f"st{f}{b}",
        "run out": f"run out ({fielder})" if fielder else "run out",
        "hit wicket": f"hit wicket{b}",
    }.get(k, k)


def match_scorecard(match_id: int) -> list[dict[str, Any]]:
    """Full scorecard (innings list) built from the stored performances."""
    innings = run_query(
        """SELECT i.innings_no, i.team_id, t.display_name AS team, i.runs, i.wickets, i.balls, i.extras, i.target_runs, i.declared, i.fow_json
                           FROM innings i JOIN teams t ON t.team_id = i.team_id WHERE i.match_id = :m ORDER BY i.innings_no""",
        {"m": int(match_id)},
    )
    result = []
    for inn in innings.itertuples():
        bat = run_query(
            """SELECT p.full_name AS batter, bp.runs, bp.balls_faced, bp.fours, bp.sixes, bp.strike_rate, bp.is_out, bp.dismissal_kind, bw.full_name AS bowler, bp.dismissal_fielder AS fielder
                           FROM batting_performances bp JOIN players p ON p.player_id = bp.player_id LEFT JOIN players bw ON bw.player_id = bp.dismissed_by_id
                           WHERE bp.match_id = :m AND bp.innings_no = :i ORDER BY bp.batting_position""",
            {"m": int(match_id), "i": int(inn.innings_no)},
        )
        bat_view = pd.DataFrame(
            {
                "Batter": bat["batter"],
                "Dismissal": [
                    _dismissal_text(
                        r.dismissal_kind, bool(r.is_out), r.bowler, r.fielder
                    )
                    for r in bat.itertuples()
                ],
                "R": bat["runs"],
                "B": bat["balls_faced"],
                "4s": bat["fours"],
                "6s": bat["sixes"],
                "SR": bat["strike_rate"],
            }
        )
        bowl = run_query(
            """SELECT p.full_name AS bowler, bp.balls_bowled, bp.maidens, bp.runs_conceded, bp.wickets, bp.economy, bp.wides, bp.no_balls
                            FROM bowling_performances bp JOIN players p ON p.player_id = bp.player_id WHERE bp.match_id = :m AND bp.innings_no = :i ORDER BY bp.wickets DESC, bp.runs_conceded""",
            {"m": int(match_id), "i": int(inn.innings_no)},
        )
        bowl_view = pd.DataFrame(
            {
                "Bowler": bowl["bowler"],
                "O": [_overs_text(int(b)) for b in bowl["balls_bowled"]],
                "M": bowl["maidens"],
                "R": bowl["runs_conceded"],
                "W": bowl["wickets"],
                "Econ": bowl["economy"],
                "WD": bowl["wides"],
                "NB": bowl["no_balls"],
            }
        )
        dnb = run_query(
            """SELECT p.full_name FROM match_players mp JOIN players p ON p.player_id = mp.player_id WHERE mp.match_id = :m AND mp.team_id = :t
                           AND mp.player_id NOT IN (SELECT player_id FROM batting_performances WHERE match_id = :m AND innings_no = :i)""",
            {"m": int(match_id), "t": int(inn.team_id), "i": int(inn.innings_no)},
        )["full_name"].tolist()
        try:
            fow = json.loads(inn.fow_json or "[]")
        except (TypeError, ValueError):
            fow = []
        fow_text = ", ".join(f"{w[0]}-{w[1]} ({w[2]}, {w[3]} ov)" for w in fow)
        total = (
            f"{int(inn.runs)}"
            if inn.wickets >= 10
            else f"{int(inn.runs)}/{int(inn.wickets)}"
        )
        result.append(
            {
                "innings_no": int(inn.innings_no),
                "team": inn.team,
                "total": f"{total} ({_overs_text(int(inn.balls))} Ov)"
                + (" d" if inn.declared else ""),
                "extras": int(inn.extras),
                "target": None if pd.isna(inn.target_runs) else int(inn.target_runs),
                "batting": bat_view,
                "bowling": bowl_view,
                "did_not_bat": dnb,
                "fow": fow_text,
            }
        )
    return result


def match_over_data(match_id: int) -> pd.DataFrame:
    """Per-over runs / wickets for the worm, run-rate and Manhattan charts."""
    rows = []
    innings = run_query(
        "SELECT i.innings_no, t.display_name AS team, i.over_runs_json FROM innings i JOIN teams t ON t.team_id = i.team_id WHERE i.match_id = :m ORDER BY i.innings_no",
        {"m": int(match_id)},
    )
    for inn in innings.itertuples():
        try:
            overs = json.loads(inn.over_runs_json or "[]")
        except (TypeError, ValueError):
            continue
        total = 0
        for number, (runs, wkts) in enumerate(overs, start=1):
            total += runs
            rows.append(
                {
                    "innings": f"{inn.team} (Inns {inn.innings_no})",
                    "over": number,
                    "runs": runs,
                    "wickets": wkts,
                    "cumulative": total,
                    "run_rate": round(total / number, 2),
                }
            )
    return pd.DataFrame(rows)


def match_squads(match_id: int) -> dict[str, pd.DataFrame]:
    df = run_query(
        """SELECT t.display_name AS team, p.full_name AS player, p.playing_role AS role FROM match_players mp JOIN players p ON p.player_id = mp.player_id
                      JOIN teams t ON t.team_id = mp.team_id WHERE mp.match_id = :m ORDER BY t.display_name, p.full_name""",
        {"m": int(match_id)},
    )
    return {
        team: group[["player", "role"]].reset_index(drop=True)
        for team, group in df.groupby("team")
    }


# ============================================================================ series
def series_list(
    *,
    year: int | None = None,
    gender: str | None = None,
    fmt: str | None = None,
    text: str | None = None,
    limit: int = 300,
) -> pd.DataFrame:
    where, params = ["1 = 1"], {"limit": int(limit)}
    if year:
        where.append("s.start_date >= :y0 AND s.start_date < :y1")
        params.update(y0=f"{int(year)}-01-01", y1=f"{int(year) + 1}-01-01")
    if gender:
        where.append("s.gender = :gender")
        params["gender"] = gender
    if fmt:
        where.append("s.match_type = :fmt")
        params["fmt"] = fmt
    if text and text.strip():
        where.append("LOWER(s.series_name) LIKE :text")
        params["text"] = f"%{text.strip().lower()}%"
    return run_query(
        f"""SELECT s.series_id, s.series_name, s.match_type AS format, s.gender, s.host_country AS host, s.start_date, s.end_date, s.total_matches AS matches
                         FROM series s WHERE {' AND '.join(where)} ORDER BY s.start_date DESC LIMIT :limit""",
        params,
    )


def series_leaders(series_id: int) -> dict[str, pd.DataFrame]:
    runs = run_query(
        """SELECT p.full_name AS player, t.display_name AS team, COUNT(*) AS inns, SUM(bp.runs) AS runs, MAX(bp.runs) AS hs
                        FROM batting_performances bp JOIN matches m ON m.match_id = bp.match_id JOIN players p ON p.player_id = bp.player_id JOIN teams t ON t.team_id = bp.team_id
                        WHERE m.series_id = :s GROUP BY p.player_id, p.full_name, t.display_name ORDER BY runs DESC LIMIT 10""",
        {"s": int(series_id)},
    )
    wkts = run_query(
        """SELECT p.full_name AS player, t.display_name AS team, SUM(bp.wickets) AS wickets, SUM(bp.runs_conceded) AS runs, ROUND(6.0 * SUM(bp.runs_conceded) / SUM(bp.balls_bowled), 2) AS econ
                        FROM bowling_performances bp JOIN matches m ON m.match_id = bp.match_id JOIN players p ON p.player_id = bp.player_id JOIN teams t ON t.team_id = bp.team_id
                        WHERE m.series_id = :s GROUP BY p.player_id, p.full_name, t.display_name ORDER BY wickets DESC, econ LIMIT 10""",
        {"s": int(series_id)},
    )
    return {"runs": runs, "wickets": wkts}


# ============================================================================ venues
def venues_overview(
    country: str | None = None, text: str | None = None, limit: int = 300
) -> pd.DataFrame:
    where, params = ["1 = 1"], {"limit": int(limit)}
    if country:
        where.append("v.country = :country")
        params["country"] = country
    if text and text.strip():
        where.append("(LOWER(v.venue_name) LIKE :t OR LOWER(v.city) LIKE :t)")
        params["t"] = f"%{text.strip().lower()}%"
    df = run_query(
        f"""
        SELECT v.venue_id, v.venue_name, v.city, v.country, v.capacity, COUNT(DISTINCT m.match_id) AS matches,
               ROUND(AVG(CASE WHEN i.innings_no = 1 THEN i.runs END), 1) AS avg_first_innings, MAX(i.runs) AS highest_total,
               SUM(CASE WHEN i.innings_no = 1 AND i.team_id = m.winner_id THEN 1 ELSE 0 END) AS bat_first_wins,
               COUNT(DISTINCT CASE WHEN m.winner_id IS NOT NULL THEN m.match_id END) AS decided
        FROM venues v JOIN matches m ON m.venue_id = v.venue_id AND m.status = 'Completed' LEFT JOIN innings i ON i.match_id = m.match_id
        WHERE {' AND '.join(where)}
        GROUP BY v.venue_id, v.venue_name, v.city, v.country, v.capacity ORDER BY matches DESC LIMIT :limit""",
        params,
    )
    df["bat_first_win_pct"] = (
        100 * df["bat_first_wins"] / df["decided"].where(df["decided"] > 0)
    ).round(1)
    return df.drop(columns=["bat_first_wins", "decided"])


def venue_countries() -> list[str]:
    return [
        c
        for c in run_query(
            "SELECT DISTINCT country FROM venues WHERE country IS NOT NULL ORDER BY country"
        )["country"]
    ]


# ============================================================================ records
_FILTERS = {
    "fmt": "m.match_format = :fmt",
    "gender": "m.gender = :gender",
    "since": "m.match_year >= :since",
}


def _filters(
    fmt: str | None, gender: str | None, since_year: int | None
) -> tuple[str, dict[str, Any]]:
    clauses, params = ["m.status = 'Completed'"], {}
    for key, value in (("fmt", fmt), ("gender", gender), ("since", since_year)):
        if value:
            clauses.append(_FILTERS[key])
            params[key] = value
    return " AND ".join(clauses), params


_BATTING_ORDER = {
    "Most runs": ("runs", None),
    "Best average": ("avg", "COUNT(*) >= :min_inns"),
    "Best strike rate": ("sr", "SUM(b.balls_faced) >= :min_balls"),
    "Most hundreds": ("hundreds", None),
    "Most fifties": ("fifties", None),
    "Most sixes": ("sixes", None),
    "Most fours": ("fours", None),
    "Most ducks": ("ducks", None),
}
BATTING_KINDS = list(_BATTING_ORDER) + ["Highest score"]


def batting_records(
    kind: str,
    fmt: str | None = None,
    gender: str | None = None,
    since_year: int | None = None,
    limit: int = 25,
) -> pd.DataFrame:
    """Batting leaderboards computed from the stored innings."""
    if kind not in BATTING_KINDS:
        raise ValidationError("Unknown batting record.")
    where, params = _filters(fmt, gender, since_year)
    params["limit"] = int(limit)
    if kind == "Highest score":
        return run_query(
            f"""SELECT p.full_name AS player, t.display_name AS team, b.runs, b.balls_faced AS balls, b.fours AS "4s", b.sixes AS "6s", b.strike_rate AS sr,
                                    CASE WHEN b.is_out THEN 'out' ELSE 'not out' END AS status, CASE WHEN m.team1_id = b.team_id THEN t2.display_name ELSE t1.display_name END AS opponent, m.match_date AS date, m.match_format AS format
                             FROM batting_performances b JOIN matches m ON m.match_id = b.match_id JOIN players p ON p.player_id = b.player_id JOIN teams t ON t.team_id = b.team_id
                             JOIN teams t1 ON t1.team_id = m.team1_id JOIN teams t2 ON t2.team_id = m.team2_id WHERE {where} ORDER BY b.runs DESC, b.balls_faced LIMIT :limit""",
            params,
        )
    column, having = _BATTING_ORDER[kind]
    params.update(
        min_inns=20, min_balls=500
    )  # minimum innings / balls so tiny samples do not top the lists
    having_sql = f"HAVING {having}" if having else ""
    return run_query(
        f"""SELECT p.full_name AS player, t.display_name AS team, COUNT(*) AS inns, SUM(b.runs) AS runs,
                                ROUND(1.0 * SUM(b.runs) / NULLIF(SUM(CASE WHEN b.is_out THEN 1 ELSE 0 END), 0), 2) AS avg,
                                ROUND(100.0 * SUM(b.runs) / NULLIF(SUM(b.balls_faced), 0), 2) AS sr,
                                SUM(CASE WHEN b.runs >= 100 THEN 1 ELSE 0 END) AS hundreds, SUM(CASE WHEN b.runs >= 50 AND b.runs < 100 THEN 1 ELSE 0 END) AS fifties,
                                SUM(b.fours) AS fours, SUM(b.sixes) AS sixes, SUM(CASE WHEN b.runs = 0 AND b.is_out THEN 1 ELSE 0 END) AS ducks
                         FROM batting_performances b JOIN matches m ON m.match_id = b.match_id JOIN players p ON p.player_id = b.player_id JOIN teams t ON t.team_id = p.team_id
                         WHERE {where} GROUP BY p.player_id, p.full_name, t.display_name {having_sql} ORDER BY {column} DESC LIMIT :limit""",
        params,
    )


_BOWLING_ORDER = {
    "Most wickets": "wickets DESC",
    "Best economy": "econ ASC",
    "Best average": "avg ASC",
    "Best strike rate": "sr ASC",
    "Most 5-wicket hauls": "five_fors DESC",
    "Most maidens": "maidens DESC",
}
BOWLING_KINDS = list(_BOWLING_ORDER) + ["Best figures"]


def bowling_records(
    kind: str,
    fmt: str | None = None,
    gender: str | None = None,
    since_year: int | None = None,
    limit: int = 25,
) -> pd.DataFrame:
    if kind not in BOWLING_KINDS:
        raise ValidationError("Unknown bowling record.")
    where, params = _filters(fmt, gender, since_year)
    params["limit"] = int(limit)
    if kind == "Best figures":
        return run_query(
            f"""SELECT p.full_name AS player, t.display_name AS team, bw.wickets || '/' || bw.runs_conceded AS figures, ROUND(bw.balls_bowled / 6.0, 1) AS overs, bw.economy AS econ,
                                    CASE WHEN m.team1_id = bw.team_id THEN t2.display_name ELSE t1.display_name END AS opponent, m.match_date AS date, m.match_format AS format
                             FROM bowling_performances bw JOIN matches m ON m.match_id = bw.match_id JOIN players p ON p.player_id = bw.player_id JOIN teams t ON t.team_id = bw.team_id
                             JOIN teams t1 ON t1.team_id = m.team1_id JOIN teams t2 ON t2.team_id = m.team2_id WHERE {where} ORDER BY bw.wickets DESC, bw.runs_conceded ASC LIMIT :limit""",
            params,
        )
    having = {
        "Best economy": "HAVING SUM(bw.balls_bowled) >= 300",
        "Best average": "HAVING SUM(bw.wickets) >= 20",
        "Best strike rate": "HAVING SUM(bw.wickets) >= 20",
    }.get(kind, "")
    return run_query(
        f"""SELECT p.full_name AS player, t.display_name AS team, COUNT(*) AS inns, SUM(bw.wickets) AS wickets, SUM(bw.runs_conceded) AS runs,
                                ROUND(6.0 * SUM(bw.runs_conceded) / SUM(bw.balls_bowled), 2) AS econ, ROUND(1.0 * SUM(bw.runs_conceded) / NULLIF(SUM(bw.wickets), 0), 2) AS avg,
                                ROUND(1.0 * SUM(bw.balls_bowled) / NULLIF(SUM(bw.wickets), 0), 1) AS sr, SUM(CASE WHEN bw.wickets >= 5 THEN 1 ELSE 0 END) AS five_fors, SUM(bw.maidens) AS maidens
                         FROM bowling_performances bw JOIN matches m ON m.match_id = bw.match_id JOIN players p ON p.player_id = bw.player_id JOIN teams t ON t.team_id = p.team_id
                         WHERE {where} GROUP BY p.player_id, p.full_name, t.display_name {having} ORDER BY {_BOWLING_ORDER[kind]} LIMIT :limit""",
        params,
    )


TEAM_KINDS = [
    "Highest totals",
    "Lowest totals (all out)",
    "Biggest wins by runs",
    "Biggest wins by wickets",
    "Most wins",
]


def team_records(
    kind: str,
    fmt: str | None = None,
    gender: str | None = None,
    since_year: int | None = None,
    limit: int = 25,
) -> pd.DataFrame:
    if kind not in TEAM_KINDS:
        raise ValidationError("Unknown team record.")
    where, params = _filters(fmt, gender, since_year)
    params["limit"] = int(limit)
    innings_cols = """t.display_name AS team, i.runs, i.wickets, ROUND(i.balls / 6.0, 1) AS overs,
                      CASE WHEN m.team1_id = i.team_id THEN t2.display_name ELSE t1.display_name END AS opponent, v.venue_name AS venue, m.match_date AS date, m.match_format AS format"""
    joins = "JOIN matches m ON m.match_id = i.match_id JOIN teams t ON t.team_id = i.team_id JOIN teams t1 ON t1.team_id = m.team1_id JOIN teams t2 ON t2.team_id = m.team2_id JOIN venues v ON v.venue_id = m.venue_id"
    if kind == "Highest totals":
        return run_query(
            f"SELECT {innings_cols} FROM innings i {joins} WHERE {where} ORDER BY i.runs DESC LIMIT :limit",
            params,
        )
    if kind == "Lowest totals (all out)":
        return run_query(
            f"SELECT {innings_cols} FROM innings i {joins} WHERE {where} AND i.wickets >= 10 AND i.balls >= 30 ORDER BY i.runs ASC LIMIT :limit",
            params,
        )
    if kind in ("Biggest wins by runs", "Biggest wins by wickets"):
        vtype = "runs" if kind.endswith("runs") else "wickets"
        params["vtype"] = vtype
        return run_query(
            f"""SELECT w.display_name AS winner, m.victory_margin AS margin, m.victory_type AS type, CASE WHEN m.winner_id = m.team1_id THEN t2.display_name ELSE t1.display_name END AS opponent,
                                    v.venue_name AS venue, m.match_date AS date, m.match_format AS format
                             FROM matches m JOIN teams w ON w.team_id = m.winner_id JOIN teams t1 ON t1.team_id = m.team1_id JOIN teams t2 ON t2.team_id = m.team2_id JOIN venues v ON v.venue_id = m.venue_id
                             WHERE {where} AND m.victory_type = :vtype ORDER BY m.victory_margin DESC LIMIT :limit""",
            params,
        )
    return run_query(
        f"""SELECT w.display_name AS team, COUNT(*) AS wins FROM matches m JOIN teams w ON w.team_id = m.winner_id WHERE {where} GROUP BY w.team_id, w.display_name ORDER BY wins DESC LIMIT :limit""",
        params,
    )


FIELDING_KINDS = ["Most catches", "Most stumpings", "Most run-outs"]


def fielding_records(
    kind: str,
    fmt: str | None = None,
    gender: str | None = None,
    since_year: int | None = None,
    limit: int = 25,
) -> pd.DataFrame:
    column = {
        "Most catches": "catches",
        "Most stumpings": "stumpings",
        "Most run-outs": "run_outs",
    }.get(kind)
    if column is None:
        raise ValidationError("Unknown fielding record.")
    where, params = _filters(fmt, gender, since_year)
    params["limit"] = int(limit)
    return run_query(
        f"""SELECT p.full_name AS player, t.display_name AS team, SUM(f.catches) AS catches, SUM(f.stumpings) AS stumpings, SUM(f.run_outs) AS run_outs
                         FROM fielding_performances f JOIN matches m ON m.match_id = f.match_id JOIN players p ON p.player_id = f.player_id JOIN teams t ON t.team_id = p.team_id
                         WHERE {where} GROUP BY p.player_id, p.full_name, t.display_name ORDER BY SUM(f.{column}) DESC LIMIT :limit""",
        params,
    )


def runiq_leaderboard(fmt: str, gender: str, limit: int = 20) -> pd.DataFrame:
    """RunIQ Index = the weighted batting + bowling + fielding points formula from the project brief (Q21)."""
    return run_query(
        """
        SELECT p.full_name AS player, t.display_name AS team, p.playing_role AS role, cs.matches,
               ROUND((cs.runs * 0.01) + (cs.batting_avg * 0.5) + (cs.strike_rate * 0.3)
                     + CASE WHEN cs.wickets > 0 THEN (cs.wickets * 2) + ((50 - cs.bowling_avg) * 0.5) + ((6 - cs.economy) * 2) ELSE 0 END
                     + (cs.catches * 3) + (cs.stumpings * 5), 1) AS runiq_index
        FROM player_career_stats cs JOIN players p ON p.player_id = cs.player_id JOIN teams t ON t.team_id = p.team_id
        WHERE cs.match_format = :fmt AND p.gender = :gender AND cs.matches >= 10 ORDER BY runiq_index DESC LIMIT :limit""",
        {"fmt": fmt, "gender": gender, "limit": int(limit)},
    )
