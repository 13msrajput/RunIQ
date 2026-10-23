"""Relational schema (single source of truth) defined with SQLAlchemy Core.

Defining tables in Python keeps the project *database agnostic*: the same
definitions create the schema on SQLite, PostgreSQL or MySQL. A plain-SQL copy is
exported to ``sql/schema.sql`` by ``python -m scripts.export_sql``.

Data model (real data):
    teams, venues, players, series  -> reference data
    matches, innings, match_players -> one row per real match / innings / squad member
    batting_performances, bowling_performances, fielding_performances -> per-match player stats
    player_career_stats             -> aggregated per player and format (rebuilt after each import)
    ranking_snapshots, api_sync_log -> data stored from the Cricbuzz API
"""

from __future__ import annotations

from sqlalchemy import (  # SQLAlchemy building blocks
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)

from models.constants import (  # allowed values for CHECK constraints
    FORMATS,
    GENDERS,
    MATCH_STATUSES,
    RESULT_TYPES,
    ROLES,
    TOSS_DECISIONS,
    VICTORY_TYPES,
)

metadata = MetaData()  # registry that holds every table
DEC = Numeric(10, 2, asdecimal=False)  # 2-decimal numbers returned as float


def _in(column: str, values: tuple[str, ...]) -> str:
    """Build a SQL fragment like ``column IN ('a','b')``."""
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


# ---------------------------------------------------------------- teams
teams = Table(
    "teams",
    metadata,
    Column("team_id", Integer, primary_key=True, autoincrement=True),  # surrogate key
    Column(
        "team_name", String(80), nullable=False
    ),  # e.g. India (same name for men and women)
    Column("gender", String(6), nullable=False, default="male"),  # male / female
    Column("display_name", String(100), nullable=False),  # "India" or "India Women"
    Column("short_name", String(10)),  # IND
    Column("country", String(80), nullable=False),  # used for home / away logic
    Column("api_team_id", Integer),  # id in the Cricbuzz API (optional)
    UniqueConstraint("team_name", "gender", name="uq_teams_name_gender"),
    CheckConstraint(_in("gender", GENDERS), name="ck_teams_gender"),
)

# --------------------------------------------------------------- venues
venues = Table(
    "venues",
    metadata,
    Column("venue_id", Integer, primary_key=True, autoincrement=True),
    Column("venue_name", String(160), nullable=False),  # stadium name
    Column("city", String(80), nullable=False, default="Unknown"),
    Column("country", String(80)),  # derived (see models/venue_reference.py)
    Column(
        "capacity", Integer
    ),  # seating capacity (approximate, static reference list)
    Column("api_venue_id", Integer),  # id in the Cricbuzz API (optional)
    UniqueConstraint("venue_name", "city", name="uq_venues_name_city"),
    CheckConstraint("capacity IS NULL OR capacity > 0", name="ck_venues_capacity"),
)

# -------------------------------------------------------------- players
players = Table(
    "players",
    metadata,
    Column("player_id", Integer, primary_key=True, autoincrement=True),
    Column(
        "full_name", String(100), nullable=False
    ),  # name as used by Cricsheet, e.g. "V Kohli"
    Column("cricsheet_id", String(16), unique=True),  # 8-character Cricsheet person id
    Column("api_player_id", Integer),  # Cricbuzz player id when known
    Column(
        "team_id",
        Integer,
        ForeignKey("teams.team_id", ondelete="RESTRICT"),
        nullable=False,
    ),  # main national team
    Column("gender", String(6), nullable=False, default="male"),
    Column(
        "playing_role", String(30), nullable=False, default="Batsman"
    ),  # derived from match data
    Column(
        "batting_style", String(30)
    ),  # not in Cricsheet -> NULL unless entered / enriched
    Column("bowling_style", String(40)),
    Column("date_of_birth", Date),
    Column(
        "is_active", Boolean, nullable=False, default=True
    ),  # played in the last 2 years
    Column("first_match_date", Date),
    Column("last_match_date", Date),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    CheckConstraint(_in("playing_role", ROLES), name="ck_players_role"),
    CheckConstraint(_in("gender", GENDERS), name="ck_players_gender"),
)

# --------------------------------------------------------------- series
series = Table(
    "series",
    metadata,
    Column("series_id", Integer, primary_key=True, autoincrement=True),
    Column("series_name", String(200), nullable=False),
    Column("season", String(20)),  # e.g. 2025/26
    Column("gender", String(6), nullable=False, default="male"),
    Column("host_country", String(80)),
    Column("match_type", String(10), nullable=False),  # Test / ODI / T20I
    Column("start_date", Date, nullable=False),
    Column("end_date", Date),
    Column("total_matches", Integer),
    Column("api_series_id", Integer),
    UniqueConstraint(
        "series_name", "gender", "match_type", name="uq_series_name_gender_type"
    ),
    CheckConstraint(_in("match_type", FORMATS), name="ck_series_type"),
    CheckConstraint(_in("gender", GENDERS), name="ck_series_gender"),
)

# -------------------------------------------------------------- matches
matches = Table(
    "matches",
    metadata,
    Column("match_id", Integer, primary_key=True, autoincrement=True),
    Column("cricsheet_id", String(20), unique=True),  # file name of the Cricsheet match
    Column("api_match_id", Integer, unique=True),  # id in the Cricbuzz API
    Column("series_id", Integer, ForeignKey("series.series_id", ondelete="SET NULL")),
    Column("match_desc", String(100), nullable=False),  # e.g. "2nd T20I"
    Column("match_format", String(10), nullable=False),
    Column("gender", String(6), nullable=False, default="male"),
    Column(
        "team1_id",
        Integer,
        ForeignKey("teams.team_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "team2_id",
        Integer,
        ForeignKey("teams.team_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "venue_id",
        Integer,
        ForeignKey("venues.venue_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("match_date", Date, nullable=False),
    Column("end_date", Date),
    Column("status", String(12), nullable=False, default="Completed"),
    Column("toss_winner_id", Integer, ForeignKey("teams.team_id", ondelete="RESTRICT")),
    Column("toss_decision", String(5)),  # bat / bowl
    Column("winner_id", Integer, ForeignKey("teams.team_id", ondelete="RESTRICT")),
    Column("victory_margin", Integer),
    Column(
        "victory_type", String(12)
    ),  # runs / wickets / innings / super_over / bowl_out
    Column(
        "result", String(10), nullable=False, default="normal"
    ),  # normal / tie / no result / draw
    Column(
        "dls_method", Boolean, nullable=False, default=False
    ),  # decided by Duckworth-Lewis(-Stern)
    Column(
        "player_of_match_id",
        Integer,
        ForeignKey("players.player_id", ondelete="SET NULL"),
    ),
    Column("overs_limit", Integer),  # 20, 50 ... (NULL for Tests)
    Column(
        "match_year", Integer, nullable=False
    ),  # derived from match_date (fast, portable GROUP BY)
    Column("match_quarter", Integer, nullable=False),  # 1-4, derived from match_date
    Column(
        "source", String(12), nullable=False, default="cricsheet"
    ),  # cricsheet / api / manual
    CheckConstraint("team1_id <> team2_id", name="ck_matches_distinct_teams"),
    CheckConstraint(_in("match_format", FORMATS), name="ck_matches_format"),
    CheckConstraint(_in("gender", GENDERS), name="ck_matches_gender"),
    CheckConstraint(_in("status", MATCH_STATUSES), name="ck_matches_status"),
    CheckConstraint(_in("result", RESULT_TYPES), name="ck_matches_result"),
    CheckConstraint(
        "toss_decision IS NULL OR " + _in("toss_decision", TOSS_DECISIONS),
        name="ck_matches_toss",
    ),
    CheckConstraint(
        "victory_type IS NULL OR " + _in("victory_type", VICTORY_TYPES),
        name="ck_matches_vtype",
    ),
    CheckConstraint(
        "victory_margin IS NULL OR victory_margin >= 0", name="ck_matches_margin"
    ),
    CheckConstraint(
        "winner_id IS NULL OR winner_id = team1_id OR winner_id = team2_id",
        name="ck_matches_winner",
    ),
    CheckConstraint("match_quarter BETWEEN 1 AND 4", name="ck_matches_quarter"),
)

# --------------------------------------------------------- squad members
match_players = Table(
    "match_players",
    metadata,
    Column(
        "match_id",
        Integer,
        ForeignKey("matches.match_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "player_id",
        Integer,
        ForeignKey("players.player_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "team_id",
        Integer,
        ForeignKey("teams.team_id", ondelete="RESTRICT"),
        nullable=False,
    ),
)

# ------------------------------------------------------------- innings
innings = Table(
    "innings",
    metadata,
    Column("innings_id", Integer, primary_key=True, autoincrement=True),
    Column(
        "match_id",
        Integer,
        ForeignKey("matches.match_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("innings_no", Integer, nullable=False),
    Column(
        "team_id",
        Integer,
        ForeignKey("teams.team_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("runs", Integer, nullable=False, default=0),
    Column("wickets", Integer, nullable=False, default=0),
    Column("balls", Integer, nullable=False, default=0),  # legal deliveries bowled
    Column("extras", Integer, nullable=False, default=0),
    Column("target_runs", Integer),  # target set for this innings (chases)
    Column("declared", Boolean, nullable=False, default=False),
    Column(
        "over_runs_json", Text
    ),  # [[runs, wickets], ...] one entry per over (worm / run-rate charts)
    Column("fow_json", Text),  # [[wicket_no, team_score, player_out, over], ...]
    UniqueConstraint("match_id", "innings_no", name="uq_innings_match_no"),
)

# ------------------------------------------------- batting performances
batting_performances = Table(
    "batting_performances",
    metadata,
    Column("perf_id", Integer, primary_key=True, autoincrement=True),
    Column(
        "match_id",
        Integer,
        ForeignKey("matches.match_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("innings_no", Integer, nullable=False),
    Column(
        "player_id",
        Integer,
        ForeignKey("players.player_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "team_id",
        Integer,
        ForeignKey("teams.team_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "batting_position", Integer, nullable=False
    ),  # order of arrival at the crease
    Column("runs", Integer, nullable=False, default=0),
    Column("balls_faced", Integer, nullable=False, default=0),
    Column("fours", Integer, nullable=False, default=0),
    Column("sixes", Integer, nullable=False, default=0),
    Column("strike_rate", DEC),
    Column("is_out", Boolean, nullable=False, default=True),
    Column("dismissal_kind", String(30)),  # bowled, caught, lbw ...
    Column(
        "dismissed_by_id", Integer
    ),  # bowler credited (no FK on purpose - keeps deletes simple)
    Column(
        "dismissal_fielder", String(100)
    ),  # catcher / stumper / run-out fielder(s) as text
    UniqueConstraint(
        "match_id", "innings_no", "player_id", name="uq_batting_match_innings_player"
    ),
    CheckConstraint("runs >= 0 AND balls_faced >= 0", name="ck_batting_non_negative"),
    CheckConstraint("batting_position >= 1", name="ck_batting_position"),
)

# ------------------------------------------------- bowling performances
bowling_performances = Table(
    "bowling_performances",
    metadata,
    Column("perf_id", Integer, primary_key=True, autoincrement=True),
    Column(
        "match_id",
        Integer,
        ForeignKey("matches.match_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("innings_no", Integer, nullable=False),
    Column(
        "player_id",
        Integer,
        ForeignKey("players.player_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "team_id",
        Integer,
        ForeignKey("teams.team_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("balls_bowled", Integer, nullable=False),  # legal balls; overs = balls / 6
    Column("maidens", Integer, nullable=False, default=0),
    Column("runs_conceded", Integer, nullable=False, default=0),
    Column("wickets", Integer, nullable=False, default=0),
    Column("economy", DEC),
    Column("wides", Integer, nullable=False, default=0),
    Column("no_balls", Integer, nullable=False, default=0),
    UniqueConstraint(
        "match_id", "innings_no", "player_id", name="uq_bowling_match_innings_player"
    ),
    CheckConstraint(
        "balls_bowled > 0 AND runs_conceded >= 0 AND wickets BETWEEN 0 AND 10",
        name="ck_bowling_values",
    ),
)

# ------------------------------------------------- fielding performances
fielding_performances = Table(
    "fielding_performances",
    metadata,
    Column("perf_id", Integer, primary_key=True, autoincrement=True),
    Column(
        "match_id",
        Integer,
        ForeignKey("matches.match_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "player_id",
        Integer,
        ForeignKey("players.player_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "team_id",
        Integer,
        ForeignKey("teams.team_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("catches", Integer, nullable=False, default=0),
    Column("stumpings", Integer, nullable=False, default=0),
    Column("run_outs", Integer, nullable=False, default=0),
    UniqueConstraint("match_id", "player_id", name="uq_fielding_match_player"),
)

# ----------------------------------------------- career statistics
player_career_stats = Table(
    "player_career_stats",
    metadata,
    Column(
        "player_id",
        Integer,
        ForeignKey("players.player_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("match_format", String(10), primary_key=True),  # composite primary key
    Column("matches", Integer, nullable=False, default=0),
    Column("innings", Integer, nullable=False, default=0),
    Column("not_outs", Integer, nullable=False, default=0),
    Column("runs", Integer, nullable=False, default=0),
    Column("balls_faced", Integer, nullable=False, default=0),
    Column("highest_score", Integer, nullable=False, default=0),
    Column("batting_avg", DEC, nullable=False, default=0),
    Column("strike_rate", DEC, nullable=False, default=0),
    Column("centuries", Integer, nullable=False, default=0),
    Column("fifties", Integer, nullable=False, default=0),
    Column("wickets", Integer, nullable=False, default=0),
    Column("bowling_avg", DEC),  # NULL when the player never took a wicket
    Column("economy", DEC),  # NULL when the player never bowled
    Column("catches", Integer, nullable=False, default=0),
    Column("stumpings", Integer, nullable=False, default=0),
    CheckConstraint(_in("match_format", FORMATS), name="ck_career_format"),
    CheckConstraint("not_outs <= innings", name="ck_career_not_outs"),
)

# --------------------------------------------- ranking snapshots (API)
ranking_snapshots = Table(
    "ranking_snapshots",
    metadata,
    Column("snapshot_id", Integer, primary_key=True, autoincrement=True),
    Column(
        "category", String(20), nullable=False
    ),  # batsmen / bowlers / allrounders / teams
    Column("match_format", String(10), nullable=False),  # test / odi / t20
    Column("gender", String(6), nullable=False),  # male / female
    Column("rank_pos", Integer),
    Column("name", String(120), nullable=False),
    Column("country", String(80)),
    Column("rating", Integer),
    Column("points", Integer),
    Column("fetched_at", DateTime, server_default=func.current_timestamp()),
)

# ------------------------------------------------------- API sync log
api_sync_log = Table(
    "api_sync_log",
    metadata,
    Column("log_id", Integer, primary_key=True, autoincrement=True),
    Column("endpoint", String(120), nullable=False),
    Column("status", String(12), nullable=False),  # success / failed
    Column("records_processed", Integer, nullable=False, default=0),
    Column("message", String(400)),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
)

# ------------------------------------------------------------- indexes
Index("ix_players_team_id", players.c.team_id)  # squad lists
Index("ix_players_role", players.c.playing_role)  # GROUP BY role (Q6)
Index("ix_players_name", players.c.full_name)  # name search
Index("ix_matches_date", matches.c.match_date)  # date filters / ORDER BY
Index(
    "ix_matches_status_date", matches.c.status, matches.c.match_date
)  # "last N completed matches"
Index("ix_matches_format_gender", matches.c.match_format, matches.c.gender)
Index("ix_matches_team1", matches.c.team1_id)
Index("ix_matches_team2", matches.c.team2_id)
Index("ix_matches_winner", matches.c.winner_id)
Index("ix_matches_venue", matches.c.venue_id)
Index("ix_matches_series", matches.c.series_id)
Index("ix_matches_year_quarter", matches.c.match_year, matches.c.match_quarter)
Index("ix_series_start_date", series.c.start_date)
Index("ix_match_players_player", match_players.c.player_id)  # appearances per player
Index("ix_innings_match", innings.c.match_id)
Index("ix_batting_player", batting_performances.c.player_id)  # player level aggregates
Index(
    "ix_batting_match_innings",
    batting_performances.c.match_id,
    batting_performances.c.innings_no,
    batting_performances.c.team_id,
    batting_performances.c.batting_position,
)  # partnership joins
Index("ix_bowling_player", bowling_performances.c.player_id)
Index("ix_bowling_match", bowling_performances.c.match_id)
Index("ix_fielding_player", fielding_performances.c.player_id)
Index("ix_career_format", player_career_stats.c.match_format)
Index(
    "ix_rankings_lookup",
    ranking_snapshots.c.category,
    ranking_snapshots.c.match_format,
    ranking_snapshots.c.gender,
)
