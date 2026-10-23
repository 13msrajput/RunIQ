"""The 25 SQL practice questions from the project brief (plus Q22B), written for the REAL-data schema.

Each entry is an ``AnalyticsQuery``: the business question, the SQL, and an optional
factory producing bind parameters (so dates are always relative to "today").
Everything is parameterized - no string formatting of user data.

NOTE: SQL comments below deliberately avoid the colon character, because
SQLAlchemy's text() would mistake ':word' for a bind parameter.
"""

from __future__ import annotations

from dataclasses import dataclass, field  # structured query records
from datetime import date, timedelta  # relative date parameters
from typing import Callable  # type hint for the parameter factory


@dataclass(frozen=True)
class AnalyticsQuery:
    """One analytics question and the SQL that answers it."""

    number: str  # "1" ... "25", "22B"
    level: str  # Beginner / Intermediate / Advanced
    title: str  # short name shown in the UI
    question: str  # business problem in plain English
    concepts: str  # SQL concepts practiced
    sql: str  # the query itself
    params: Callable[[], dict] = field(default=lambda: {})  # bind-parameter factory

    @property
    def label(self) -> str:
        """Text used in the select box."""
        return f"Q{self.number} - {self.title}"


def _iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _last_30_days() -> dict:
    return {"since_date": _iso(30), "today": date.today().isoformat()}


def _year_2024() -> dict:
    return {"year_start": "2024-01-01", "year_end": "2025-01-01"}


def _since_2020() -> dict:
    return {"since_date": "2020-01-01"}


def _since_2022() -> dict:
    return {"since_date": "2022-01-01"}


def _last_3_years() -> dict:
    return {"since_date": _iso(3 * 365)}


def _recent_form() -> dict:
    return {"active_since": _iso(365)}


B, I, A = "Beginner", "Intermediate", "Advanced"  # level labels

QUERIES: list[AnalyticsQuery] = [
    # ------------------------------------------------------------------ BEGINNER
    AnalyticsQuery(
        "1",
        B,
        "Indian players",
        "Find all players who represent India (men and women) with their name, playing role, batting style and bowling style.",
        "SELECT, JOIN, WHERE, ORDER BY, COALESCE",
        """
SELECT p.full_name,                                   -- player name as recorded by Cricsheet
       t.display_name AS team,                        -- India or India Women
       p.playing_role,                                -- derived from match data
       COALESCE(p.batting_style, 'Not recorded') AS batting_style,    -- replace NULL with text
       COALESCE(p.bowling_style, 'Not recorded') AS bowling_style
FROM players p
JOIN teams t ON t.team_id = p.team_id                 -- link player to team
WHERE t.team_name = 'India'                           -- only the Indian squads
ORDER BY t.gender DESC, p.full_name
""",
    ),
    AnalyticsQuery(
        "2",
        B,
        "Matches in last 30 days",
        "Show completed matches from the last 30 days with description, both teams, venue and city, newest first.",
        "Multiple JOINs to the same table (aliases), date filter, ORDER BY DESC",
        """
SELECT m.match_date,
       m.match_desc,                                  -- e.g. 2nd T20I
       m.match_format,
       t1.display_name AS team1,                      -- first team
       t2.display_name AS team2,                      -- second team (same table, new alias)
       v.venue_name,
       v.city
FROM matches m
JOIN teams t1 ON t1.team_id = m.team1_id
JOIN teams t2 ON t2.team_id = m.team2_id
JOIN venues v ON v.venue_id = m.venue_id
WHERE m.status = 'Completed'
  AND m.match_date >= :since_date                     -- 30 days ago (bind parameter)
  AND m.match_date <= :today
ORDER BY m.match_date DESC, m.match_id DESC           -- most recent first
""",
        _last_30_days,
    ),
    AnalyticsQuery(
        "3",
        B,
        "Top 10 ODI run scorers",
        "List the 10 highest run scorers in ODI cricket with total runs, batting average and centuries.",
        "JOIN, WHERE, ORDER BY, LIMIT",
        """
SELECT p.full_name AS player_name,
       t.display_name AS team,
       cs.runs AS total_runs,
       cs.batting_avg,
       cs.centuries
FROM player_career_stats cs
JOIN players p ON p.player_id = cs.player_id
JOIN teams t ON t.team_id = p.team_id
WHERE cs.match_format = 'ODI'                         -- only ODI rows
ORDER BY cs.runs DESC                                 -- highest first
LIMIT 10
""",
    ),
    AnalyticsQuery(
        "4",
        B,
        "Large venues (50,000+)",
        "Display venues with seating capacity above 50,000, largest first (capacities come from a static reference list).",
        "WHERE with comparison, ORDER BY",
        """
SELECT venue_name, city, country, capacity
FROM venues
WHERE capacity > 50000                                -- strictly more than 50,000
ORDER BY capacity DESC
""",
    ),
    AnalyticsQuery(
        "5",
        B,
        "Wins per team",
        "Calculate how many matches each team has won, most wins first.",
        "GROUP BY, COUNT, JOIN",
        """
SELECT t.display_name AS team_name,
       COUNT(*) AS total_wins                         -- one row per won match
FROM matches m
JOIN teams t ON t.team_id = m.winner_id               -- winner only (NULL winners drop out of the join)
WHERE m.status = 'Completed'
GROUP BY t.team_id, t.display_name
ORDER BY total_wins DESC, t.display_name
""",
    ),
    AnalyticsQuery(
        "6",
        B,
        "Players per role",
        "Count how many players belong to each playing role (men and women).",
        "GROUP BY, COUNT",
        """
SELECT playing_role,
       gender,
       COUNT(*) AS player_count
FROM players
GROUP BY playing_role, gender
ORDER BY player_count DESC
""",
    ),
    AnalyticsQuery(
        "7",
        B,
        "Highest score per format",
        "Find the highest individual batting score in each format (Test, ODI, T20I).",
        "Correlated subquery, MAX",
        """
SELECT cs.match_format,
       cs.highest_score,
       p.full_name AS player_name,                    -- who scored it
       t.display_name AS team
FROM player_career_stats cs
JOIN players p ON p.player_id = cs.player_id
JOIN teams t ON t.team_id = p.team_id
WHERE cs.highest_score = (                            -- keep only the maximum of its own format
        SELECT MAX(x.highest_score)
        FROM player_career_stats x
        WHERE x.match_format = cs.match_format)
ORDER BY cs.highest_score DESC
""",
    ),
    AnalyticsQuery(
        "8",
        B,
        "Series starting in 2024",
        "Show all series that started in 2024 with host country, match type, start date and number of matches.",
        "Date range filter (sargable)",
        """
SELECT series_name, host_country, match_type, gender, start_date, total_matches
FROM series
WHERE start_date >= :year_start                       -- 2024-01-01 inclusive
  AND start_date <  :year_end                         -- 2025-01-01 exclusive (index friendly)
ORDER BY start_date
""",
        _year_2024,
    ),
    # -------------------------------------------------------------- INTERMEDIATE
    AnalyticsQuery(
        "9",
        I,
        "All-rounders 1000+ runs and 50+ wickets",
        "Find all-rounders with more than 1000 career runs AND more than 50 wickets, per format.",
        "Multiple conditions, JOIN",
        """
SELECT p.full_name AS player_name,
       t.display_name AS team,
       cs.runs AS total_runs,
       cs.wickets AS total_wickets,
       cs.match_format
FROM player_career_stats cs
JOIN players p ON p.player_id = cs.player_id
JOIN teams t ON t.team_id = p.team_id
WHERE p.playing_role = 'All-rounder'
  AND cs.runs > 1000
  AND cs.wickets > 50
ORDER BY cs.runs DESC
""",
    ),
    AnalyticsQuery(
        "10",
        I,
        "Last 20 completed matches",
        "Details of the last 20 completed matches with teams, winner, margin, victory type and venue.",
        "LEFT JOIN, COALESCE, LIMIT",
        """
SELECT m.match_date,
       m.match_desc,
       t1.display_name AS team1,
       t2.display_name AS team2,
       COALESCE(w.display_name, 'No result') AS winning_team,   -- ties and washouts have no winner
       m.victory_margin,
       m.victory_type,
       v.venue_name
FROM matches m
JOIN teams t1 ON t1.team_id = m.team1_id
JOIN teams t2 ON t2.team_id = m.team2_id
JOIN venues v ON v.venue_id = m.venue_id
LEFT JOIN teams w ON w.team_id = m.winner_id          -- LEFT JOIN keeps matches without a winner
WHERE m.status = 'Completed'
ORDER BY m.match_date DESC, m.match_id DESC
LIMIT 20
""",
    ),
    AnalyticsQuery(
        "11",
        I,
        "Performance across formats",
        "For players who played at least 2 formats, show runs in Test, ODI and T20I plus overall batting average.",
        "Conditional aggregation (CASE), HAVING, NULLIF",
        """
SELECT p.full_name,
       SUM(CASE WHEN cs.match_format = 'Test' THEN cs.runs ELSE 0 END) AS test_runs,
       SUM(CASE WHEN cs.match_format = 'ODI'  THEN cs.runs ELSE 0 END) AS odi_runs,
       SUM(CASE WHEN cs.match_format = 'T20I' THEN cs.runs ELSE 0 END) AS t20i_runs,
       ROUND(1.0 * SUM(cs.runs) / NULLIF(SUM(cs.innings - cs.not_outs), 0), 2) AS overall_batting_avg,  -- runs / dismissals
       COUNT(DISTINCT cs.match_format) AS formats_played
FROM player_career_stats cs
JOIN players p ON p.player_id = cs.player_id
GROUP BY p.player_id, p.full_name
HAVING COUNT(DISTINCT cs.match_format) >= 2           -- at least two formats
   AND SUM(cs.innings) >= 20                          -- ignore players with tiny samples
ORDER BY overall_batting_avg DESC
""",
    ),
    AnalyticsQuery(
        "12",
        I,
        "Home vs away wins",
        "For every team count matches and wins at home (venue country = team country) versus away.",
        "CTE, UNION ALL, conditional aggregation",
        """
WITH team_matches AS (                                -- one row per team per match
    SELECT m.match_id, m.team1_id AS team_id, m.winner_id, v.country AS venue_country
    FROM matches m JOIN venues v ON v.venue_id = m.venue_id
    WHERE m.status = 'Completed' AND v.country IS NOT NULL
    UNION ALL
    SELECT m.match_id, m.team2_id, m.winner_id, v.country
    FROM matches m JOIN venues v ON v.venue_id = m.venue_id
    WHERE m.status = 'Completed' AND v.country IS NOT NULL
),
summary AS (
    SELECT t.display_name AS team_name,
           SUM(CASE WHEN tm.venue_country = t.country THEN 1 ELSE 0 END) AS home_matches,
           SUM(CASE WHEN tm.venue_country = t.country AND tm.winner_id = tm.team_id THEN 1 ELSE 0 END) AS home_wins,
           SUM(CASE WHEN tm.venue_country <> t.country THEN 1 ELSE 0 END) AS away_matches,
           SUM(CASE WHEN tm.venue_country <> t.country AND tm.winner_id = tm.team_id THEN 1 ELSE 0 END) AS away_wins
    FROM team_matches tm
    JOIN teams t ON t.team_id = tm.team_id
    GROUP BY t.team_id, t.display_name
)
SELECT team_name, home_matches, home_wins,
       ROUND(100.0 * home_wins / NULLIF(home_matches, 0), 1) AS home_win_pct,
       away_matches, away_wins,
       ROUND(100.0 * away_wins / NULLIF(away_matches, 0), 1) AS away_win_pct
FROM summary
WHERE home_matches + away_matches >= 20               -- only teams with a meaningful number of matches
ORDER BY home_wins + away_wins DESC
""",
    ),
    AnalyticsQuery(
        "13",
        I,
        "100+ partnerships (consecutive batsmen)",
        "Find consecutive batting positions whose combined runs in the same innings reach 100 or more (top 200 shown).",
        "Self-join on position + 1",
        """
SELECT p1.full_name AS batsman_1,
       p2.full_name AS batsman_2,
       b1.runs + b2.runs AS partnership_runs,
       b1.batting_position AS position_1,
       b2.batting_position AS position_2,
       b1.innings_no,
       m.match_date, m.match_desc, m.match_format
FROM batting_performances b1
JOIN batting_performances b2                          -- the next batsman in the order
  ON b2.match_id = b1.match_id
 AND b2.innings_no = b1.innings_no
 AND b2.team_id = b1.team_id
 AND b2.batting_position = b1.batting_position + 1
JOIN players p1 ON p1.player_id = b1.player_id
JOIN players p2 ON p2.player_id = b2.player_id
JOIN matches m ON m.match_id = b1.match_id
WHERE b1.runs + b2.runs >= 100
ORDER BY partnership_runs DESC
LIMIT 200
""",
    ),
    AnalyticsQuery(
        "14",
        I,
        "Bowling at venues",
        "For bowlers with 3+ matches at a venue (4+ overs bowled in each) show average economy, wickets and matches.",
        "CTE, HAVING, average of per-match ratios",
        """
WITH bowler_match AS (                                -- one row per bowler per match
    SELECT bp.player_id, m.venue_id, bp.match_id,
           SUM(bp.balls_bowled) AS balls,
           SUM(bp.runs_conceded) AS runs,
           SUM(bp.wickets) AS wkts
    FROM bowling_performances bp
    JOIN matches m ON m.match_id = bp.match_id
    GROUP BY bp.player_id, m.venue_id, bp.match_id
    HAVING SUM(bp.balls_bowled) >= 24                 -- at least 4 overs (24 balls)
)
SELECT p.full_name AS bowler,
       v.venue_name, v.city,
       COUNT(*) AS matches_played,
       SUM(bm.wkts) AS total_wickets,
       ROUND(AVG(6.0 * bm.runs / bm.balls), 2) AS avg_economy
FROM bowler_match bm
JOIN players p ON p.player_id = bm.player_id
JOIN venues v ON v.venue_id = bm.venue_id
GROUP BY bm.player_id, p.full_name, bm.venue_id, v.venue_name, v.city
HAVING COUNT(*) >= 3                                  -- 3 or more matches at the same venue
ORDER BY avg_economy ASC
LIMIT 500
""",
    ),
    AnalyticsQuery(
        "15",
        I,
        "Close-match performers",
        "Players' average runs in close matches (won by under 50 runs or under 5 wickets), matches played and matches won (min 5 close matches, top 50).",
        "CTE, CASE in aggregates",
        """
WITH close_matches AS (
    SELECT match_id, winner_id
    FROM matches
    WHERE status = 'Completed' AND winner_id IS NOT NULL
      AND ((victory_type = 'runs'    AND victory_margin < 50)
        OR (victory_type = 'wickets' AND victory_margin < 5))
)
SELECT p.full_name, t.display_name AS team,
       COUNT(DISTINCT cm.match_id) AS close_matches_played,
       ROUND(AVG(bp.runs), 2) AS avg_runs,
       SUM(CASE WHEN cm.winner_id = bp.team_id THEN 1 ELSE 0 END) AS close_matches_won
FROM batting_performances bp
JOIN close_matches cm ON cm.match_id = bp.match_id
JOIN players p ON p.player_id = bp.player_id
JOIN teams t ON t.team_id = bp.team_id
GROUP BY p.player_id, p.full_name, t.display_name
HAVING COUNT(DISTINCT cm.match_id) >= 5               -- avoid tiny samples
ORDER BY avg_runs DESC
LIMIT 50
""",
    ),
    AnalyticsQuery(
        "16",
        I,
        "Yearly batting trend (since 2020)",
        "Per player and year since 2020 show average runs per match and average strike rate (min 5 matches in the year).",
        "GROUP BY two columns, HAVING",
        """
SELECT p.full_name,
       m.match_year AS year,
       COUNT(DISTINCT bp.match_id) AS matches_played,
       ROUND(AVG(bp.runs), 2) AS avg_runs_per_match,
       ROUND(AVG(bp.strike_rate), 2) AS avg_strike_rate
FROM batting_performances bp
JOIN matches m ON m.match_id = bp.match_id
JOIN players p ON p.player_id = bp.player_id
WHERE m.match_date >= :since_date
GROUP BY p.player_id, p.full_name, m.match_year
HAVING COUNT(DISTINCT bp.match_id) >= 5
ORDER BY p.full_name, year
""",
        _since_2020,
    ),
    # ------------------------------------------------------------------ ADVANCED
    AnalyticsQuery(
        "17",
        A,
        "Toss advantage",
        "What percentage of matches are won by the team that wins the toss, split by toss decision?",
        "Conditional aggregation, UNION ALL",
        """
SELECT m.toss_decision,
       COUNT(*) AS matches_played,
       SUM(CASE WHEN m.toss_winner_id = m.winner_id THEN 1 ELSE 0 END) AS toss_winner_won,
       ROUND(100.0 * SUM(CASE WHEN m.toss_winner_id = m.winner_id THEN 1 ELSE 0 END) / COUNT(*), 2) AS win_pct
FROM matches m
WHERE m.status = 'Completed' AND m.winner_id IS NOT NULL AND m.toss_winner_id IS NOT NULL
GROUP BY m.toss_decision
UNION ALL                                             -- add an overall row
SELECT 'overall',
       COUNT(*),
       SUM(CASE WHEN toss_winner_id = winner_id THEN 1 ELSE 0 END),
       ROUND(100.0 * SUM(CASE WHEN toss_winner_id = winner_id THEN 1 ELSE 0 END) / COUNT(*), 2)
FROM matches
WHERE status = 'Completed' AND winner_id IS NOT NULL AND toss_winner_id IS NOT NULL
""",
    ),
    AnalyticsQuery(
        "18",
        A,
        "Most economical limited-overs bowlers",
        "Most economical ODI/T20I bowlers (min 10 matches and 2+ overs per match on average).",
        "CTE, aggregation over balls, HAVING",
        """
WITH bowler_totals AS (
    SELECT bp.player_id,
           COUNT(DISTINCT bp.match_id) AS matches_bowled,
           SUM(bp.balls_bowled) AS balls,
           SUM(bp.runs_conceded) AS runs,
           SUM(bp.wickets) AS wickets
    FROM bowling_performances bp
    JOIN matches m ON m.match_id = bp.match_id
    WHERE m.match_format IN ('ODI', 'T20I')
    GROUP BY bp.player_id
)
SELECT p.full_name AS bowler,
       t.display_name AS team,
       bt.matches_bowled,
       ROUND(6.0 * bt.runs / bt.balls, 2) AS economy_rate,      -- runs per over
       bt.wickets AS total_wickets
FROM bowler_totals bt
JOIN players p ON p.player_id = bt.player_id
JOIN teams t ON t.team_id = p.team_id
WHERE bt.matches_bowled >= 10
  AND (bt.balls / 6.0) / bt.matches_bowled >= 2         -- average overs per match
ORDER BY economy_rate ASC, total_wickets DESC
LIMIT 25
""",
    ),
    AnalyticsQuery(
        "19",
        A,
        "Most consistent batsmen",
        "Average runs and standard deviation for batsmen since 2022 (10+ balls faced per innings, min 10 innings). Lower deviation = more consistent.",
        "STDDEV aggregate, filtering before grouping",
        """
SELECT p.full_name,
       p.playing_role,
       COUNT(*) AS innings,
       ROUND(AVG(bp.runs), 2) AS avg_runs,
       ROUND(STDDEV(bp.runs), 2) AS std_dev_runs
FROM batting_performances bp
JOIN matches m ON m.match_id = bp.match_id
JOIN players p ON p.player_id = bp.player_id
WHERE m.match_date >= :since_date
  AND bp.balls_faced >= 10
  AND p.playing_role <> 'Bowler'                      -- the brief asks about batsmen
GROUP BY p.player_id, p.full_name, p.playing_role
HAVING COUNT(*) >= 10
ORDER BY std_dev_runs ASC
LIMIT 50
""",
        _since_2022,
    ),
    AnalyticsQuery(
        "20",
        A,
        "Matches and batting average by format",
        "Matches played and batting average in Test, ODI and T20 for players with 20+ total matches.",
        "Pivot with MAX(CASE ...), HAVING",
        """
SELECT p.full_name,
       SUM(CASE WHEN cs.match_format = 'Test' THEN cs.matches ELSE 0 END) AS test_matches,
       SUM(CASE WHEN cs.match_format = 'ODI'  THEN cs.matches ELSE 0 END) AS odi_matches,
       SUM(CASE WHEN cs.match_format = 'T20I' THEN cs.matches ELSE 0 END) AS t20_matches,
       MAX(CASE WHEN cs.match_format = 'Test' THEN cs.batting_avg END) AS test_avg,
       MAX(CASE WHEN cs.match_format = 'ODI'  THEN cs.batting_avg END) AS odi_avg,
       MAX(CASE WHEN cs.match_format = 'T20I' THEN cs.batting_avg END) AS t20_avg,
       SUM(cs.matches) AS total_matches
FROM player_career_stats cs
JOIN players p ON p.player_id = cs.player_id
GROUP BY p.player_id, p.full_name
HAVING SUM(cs.matches) >= 20
ORDER BY total_matches DESC
LIMIT 500
""",
    ),
    AnalyticsQuery(
        "21",
        A,
        "Weighted player ranking per format",
        "Rank players per format and gender with batting + bowling + fielding points (formula from the brief). Top 10 per format.",
        "Chained CTEs, RANK() window function",
        """
WITH points AS (
    SELECT cs.match_format, p.gender, p.full_name, p.playing_role,
           (cs.runs * 0.01) + (cs.batting_avg * 0.5) + (cs.strike_rate * 0.3) AS batting_points,
           CASE WHEN cs.wickets > 0                   -- bowling points only for players who bowled
                THEN (cs.wickets * 2) + ((50 - cs.bowling_avg) * 0.5) + ((6 - cs.economy) * 2)
                ELSE 0 END AS bowling_points,
           (cs.catches * 3) + (cs.stumpings * 5) AS fielding_points
    FROM player_career_stats cs
    JOIN players p ON p.player_id = cs.player_id
    WHERE cs.matches >= 10                            -- ignore players with a handful of matches
),
totals AS (
    SELECT *, batting_points + bowling_points + fielding_points AS total_points
    FROM points
),
ranked AS (
    SELECT *, RANK() OVER (PARTITION BY match_format, gender ORDER BY total_points DESC) AS rank_in_format
    FROM totals
)
SELECT match_format, gender, rank_in_format, full_name, playing_role,
       ROUND(batting_points, 2) AS batting_points,
       ROUND(bowling_points, 2) AS bowling_points,
       ROUND(fielding_points, 2) AS fielding_points,
       ROUND(total_points, 2) AS total_points
FROM ranked
WHERE rank_in_format <= 10
ORDER BY match_format, gender, rank_in_format
""",
    ),
    AnalyticsQuery(
        "22",
        A,
        "Head-to-head (last 3 years)",
        "For team pairs with 5+ matches in the last 3 years: wins, win %, average victory margins and batting-first vs bowling-first wins.",
        "CTE, normalizing pairs with CASE, conditional AVG",
        """
WITH pair_matches AS (
    SELECT CASE WHEN m.team1_id < m.team2_id THEN m.team1_id ELSE m.team2_id END AS team_a_id,   -- smaller id first
           CASE WHEN m.team1_id < m.team2_id THEN m.team2_id ELSE m.team1_id END AS team_b_id,   -- so A-vs-B equals B-vs-A
           m.winner_id, m.victory_margin, m.victory_type,
           CASE WHEN m.toss_decision = 'bat' THEN m.toss_winner_id
                WHEN m.toss_winner_id = m.team1_id THEN m.team2_id
                ELSE m.team1_id END AS bat_first_id                                         -- who batted first
    FROM matches m
    WHERE m.status = 'Completed' AND m.match_date >= :since_date AND m.toss_winner_id IS NOT NULL
)
SELECT ta.display_name AS team_a, tb.display_name AS team_b,
       COUNT(*) AS total_matches,
       SUM(CASE WHEN pm.winner_id = pm.team_a_id THEN 1 ELSE 0 END) AS team_a_wins,
       SUM(CASE WHEN pm.winner_id = pm.team_b_id THEN 1 ELSE 0 END) AS team_b_wins,
       ROUND(100.0 * SUM(CASE WHEN pm.winner_id = pm.team_a_id THEN 1 ELSE 0 END) / COUNT(*), 1) AS team_a_win_pct,
       ROUND(100.0 * SUM(CASE WHEN pm.winner_id = pm.team_b_id THEN 1 ELSE 0 END) / COUNT(*), 1) AS team_b_win_pct,
       ROUND(AVG(CASE WHEN pm.winner_id = pm.team_a_id AND pm.victory_type = 'runs'    THEN pm.victory_margin END), 1) AS a_avg_win_runs,
       ROUND(AVG(CASE WHEN pm.winner_id = pm.team_a_id AND pm.victory_type = 'wickets' THEN pm.victory_margin END), 1) AS a_avg_win_wickets,
       ROUND(AVG(CASE WHEN pm.winner_id = pm.team_b_id AND pm.victory_type = 'runs'    THEN pm.victory_margin END), 1) AS b_avg_win_runs,
       ROUND(AVG(CASE WHEN pm.winner_id = pm.team_b_id AND pm.victory_type = 'wickets' THEN pm.victory_margin END), 1) AS b_avg_win_wickets,
       SUM(CASE WHEN pm.winner_id = pm.bat_first_id THEN 1 ELSE 0 END) AS wins_batting_first,
       SUM(CASE WHEN pm.winner_id IS NOT NULL AND pm.winner_id <> pm.bat_first_id THEN 1 ELSE 0 END) AS wins_bowling_first
FROM pair_matches pm
JOIN teams ta ON ta.team_id = pm.team_a_id
JOIN teams tb ON tb.team_id = pm.team_b_id
GROUP BY pm.team_a_id, pm.team_b_id, ta.display_name, tb.display_name
HAVING COUNT(*) >= 5
ORDER BY total_matches DESC
""",
        _last_3_years,
    ),
    AnalyticsQuery(
        "22B",
        A,
        "Head-to-head by venue (companion to Q22)",
        "For the qualifying pairs of Q22, show batting-first vs bowling-first wins at each venue (top 100).",
        "CTE reuse, join of aggregates",
        """
WITH pair_matches AS (
    SELECT CASE WHEN m.team1_id < m.team2_id THEN m.team1_id ELSE m.team2_id END AS team_a_id,
           CASE WHEN m.team1_id < m.team2_id THEN m.team2_id ELSE m.team1_id END AS team_b_id,
           m.venue_id, m.winner_id,
           CASE WHEN m.toss_decision = 'bat' THEN m.toss_winner_id
                WHEN m.toss_winner_id = m.team1_id THEN m.team2_id
                ELSE m.team1_id END AS bat_first_id
    FROM matches m
    WHERE m.status = 'Completed' AND m.match_date >= :since_date AND m.toss_winner_id IS NOT NULL
),
qualified AS (                                         -- pairs with 5+ matches overall
    SELECT team_a_id, team_b_id FROM pair_matches
    GROUP BY team_a_id, team_b_id HAVING COUNT(*) >= 5
)
SELECT ta.display_name AS team_a, tb.display_name AS team_b, v.venue_name, v.city,
       COUNT(*) AS matches_at_venue,
       SUM(CASE WHEN pm.winner_id = pm.bat_first_id THEN 1 ELSE 0 END) AS wins_batting_first,
       SUM(CASE WHEN pm.winner_id IS NOT NULL AND pm.winner_id <> pm.bat_first_id THEN 1 ELSE 0 END) AS wins_bowling_first
FROM pair_matches pm
JOIN qualified q ON q.team_a_id = pm.team_a_id AND q.team_b_id = pm.team_b_id
JOIN teams ta ON ta.team_id = pm.team_a_id
JOIN teams tb ON tb.team_id = pm.team_b_id
JOIN venues v ON v.venue_id = pm.venue_id
GROUP BY ta.display_name, tb.display_name, v.venue_name, v.city
ORDER BY matches_at_venue DESC, ta.display_name
LIMIT 100
""",
        _last_3_years,
    ),
    AnalyticsQuery(
        "23",
        A,
        "Recent player form",
        "For players active in the last 12 months: last-5 vs last-10 innings averages, strike-rate trend, 50+ scores, a consistency score and a form category.",
        "ROW_NUMBER window, chained CTEs, CASE classification",
        """
WITH recent AS (
    SELECT bp.player_id, bp.runs, bp.strike_rate, m.match_date,
           ROW_NUMBER() OVER (PARTITION BY bp.player_id
                              ORDER BY m.match_date DESC, bp.perf_id DESC) AS rn      -- 1 = latest innings
    FROM batting_performances bp
    JOIN matches m ON m.match_id = bp.match_id
),
agg AS (
    SELECT player_id,
           MAX(match_date) AS last_played,
           AVG(CASE WHEN rn <= 5 THEN runs END) AS avg_last5,
           AVG(runs) AS avg_last10,
           AVG(CASE WHEN rn <= 5 THEN strike_rate END) AS sr_last5,
           AVG(CASE WHEN rn >  5 THEN strike_rate END) AS sr_prev5,
           SUM(CASE WHEN runs >= 50 THEN 1 ELSE 0 END) AS scores_50_plus,
           STDDEV(runs) AS sd_runs
    FROM recent
    WHERE rn <= 10                                                   -- last 10 innings only
    GROUP BY player_id
    HAVING COUNT(*) = 10                                             -- players with a full window
       AND MAX(match_date) >= :active_since                          -- still playing
)
SELECT p.full_name, t.display_name AS team, p.playing_role,
       ROUND(a.avg_last5, 2) AS avg_last_5,
       ROUND(a.avg_last10, 2) AS avg_last_10,
       ROUND(a.sr_last5 - a.sr_prev5, 2) AS strike_rate_trend,       -- positive = scoring faster lately
       a.scores_50_plus,
       ROUND(a.sd_runs, 2) AS std_dev_runs,
       ROUND(100.0 * a.avg_last10 / NULLIF(a.avg_last10 + a.sd_runs, 0), 1) AS consistency_score,  -- higher = steadier
       CASE WHEN a.avg_last5 >= 35 AND a.scores_50_plus >= 2 THEN 'Excellent Form'
            WHEN a.avg_last5 >= 25 AND a.scores_50_plus >= 1 THEN 'Good Form'
            WHEN a.avg_last5 >= 15 THEN 'Average Form'
            ELSE 'Poor Form' END AS form_category
FROM agg a
JOIN players p ON p.player_id = a.player_id
JOIN teams t ON t.team_id = p.team_id
ORDER BY a.avg_last5 DESC
LIMIT 500
""",
        _recent_form,
    ),
    AnalyticsQuery(
        "24",
        A,
        "Best batting partnerships",
        "Pairs batting in consecutive positions in 5+ partnerships: average runs, partnerships over 50, highest score and success rate (top 50).",
        "Self-join, normalizing pairs, aggregation",
        """
WITH partnerships AS (
    SELECT CASE WHEN b1.player_id < b2.player_id THEN b1.player_id ELSE b2.player_id END AS player_a_id,  -- pair stored in a fixed order
           CASE WHEN b1.player_id < b2.player_id THEN b2.player_id ELSE b1.player_id END AS player_b_id,
           b1.runs + b2.runs AS partnership_runs
    FROM batting_performances b1
    JOIN batting_performances b2
      ON b2.match_id = b1.match_id AND b2.innings_no = b1.innings_no
     AND b2.team_id = b1.team_id AND b2.batting_position = b1.batting_position + 1
)
SELECT pa.full_name AS player_1, pb.full_name AS player_2,
       COUNT(*) AS partnerships,
       ROUND(AVG(ps.partnership_runs), 2) AS avg_partnership_runs,
       SUM(CASE WHEN ps.partnership_runs > 50 THEN 1 ELSE 0 END) AS partnerships_over_50,
       MAX(ps.partnership_runs) AS highest_partnership,
       ROUND(100.0 * SUM(CASE WHEN ps.partnership_runs > 50 THEN 1 ELSE 0 END) / COUNT(*), 2) AS success_rate_pct
FROM partnerships ps
JOIN players pa ON pa.player_id = ps.player_a_id
JOIN players pb ON pb.player_id = ps.player_b_id
GROUP BY ps.player_a_id, ps.player_b_id, pa.full_name, pb.full_name
HAVING COUNT(*) >= 5
ORDER BY success_rate_pct DESC, avg_partnership_runs DESC
LIMIT 50
""",
    ),
    AnalyticsQuery(
        "25",
        A,
        "Career trajectory (quarterly)",
        "Quarterly batting averages, quarter-on-quarter change and career phase (Ascending / Declining / Stable) for players with 6+ qualifying quarters (3+ matches each).",
        "Multiple window functions (LAG, ROW_NUMBER, COUNT OVER), time-series logic",
        """
WITH quarterly AS (                                    -- one row per player per quarter
    SELECT bp.player_id, m.match_year, m.match_quarter,
           COUNT(DISTINCT bp.match_id) AS matches_in_quarter,
           AVG(bp.runs) AS avg_runs,
           AVG(bp.strike_rate) AS avg_sr
    FROM batting_performances bp
    JOIN matches m ON m.match_id = bp.match_id
    GROUP BY bp.player_id, m.match_year, m.match_quarter
    HAVING COUNT(DISTINCT bp.match_id) >= 3            -- at least 3 matches in the quarter
),
ordered AS (
    SELECT q.*,
           ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY match_year, match_quarter) AS seq_asc,
           ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY match_year DESC, match_quarter DESC) AS seq_desc,
           COUNT(*) OVER (PARTITION BY player_id) AS quarters_analyzed,
           LAG(avg_runs) OVER (PARTITION BY player_id ORDER BY match_year, match_quarter) AS prev_avg_runs
    FROM quarterly q
),
summary AS (
    SELECT player_id,
           MAX(quarters_analyzed) AS quarters_analyzed,
           AVG(CASE WHEN seq_asc  <= 3 THEN avg_runs END) AS early_avg_runs,   -- first three qualifying quarters
           AVG(CASE WHEN seq_desc <= 3 THEN avg_runs END) AS recent_avg_runs,  -- last three qualifying quarters
           AVG(CASE WHEN seq_asc  <= 3 THEN avg_sr END) AS early_sr,
           AVG(CASE WHEN seq_desc <= 3 THEN avg_sr END) AS recent_sr,
           SUM(CASE WHEN prev_avg_runs IS NOT NULL AND avg_runs > prev_avg_runs * 1.10 THEN 1 ELSE 0 END) AS improving_quarters,
           SUM(CASE WHEN prev_avg_runs IS NOT NULL AND avg_runs < prev_avg_runs * 0.90 THEN 1 ELSE 0 END) AS declining_quarters
    FROM ordered
    WHERE quarters_analyzed >= 6                       -- enough history
    GROUP BY player_id
)
SELECT p.full_name, s.quarters_analyzed,
       ROUND(s.early_avg_runs, 2) AS early_avg_runs,
       ROUND(s.recent_avg_runs, 2) AS recent_avg_runs,
       ROUND(100.0 * (s.recent_avg_runs - s.early_avg_runs) / NULLIF(s.early_avg_runs, 0), 1) AS runs_change_pct,
       ROUND(s.recent_sr - s.early_sr, 2) AS strike_rate_change,
       s.improving_quarters, s.declining_quarters,
       CASE WHEN s.recent_avg_runs > s.early_avg_runs * 1.10 THEN 'Career Ascending'
            WHEN s.recent_avg_runs < s.early_avg_runs * 0.90 THEN 'Career Declining'
            ELSE 'Career Stable' END AS career_phase
FROM summary s
JOIN players p ON p.player_id = s.player_id
ORDER BY runs_change_pct DESC
LIMIT 500
""",
    ),
]

QUERY_INDEX: dict[str, AnalyticsQuery] = {
    q.number: q for q in QUERIES
}  # lookup by number
