"""SQL views created on top of the base tables (read-only convenience layers)."""

from __future__ import annotations

VIEW_DEFINITIONS: list[tuple[str, str]] = [  # (view name, CREATE VIEW statement)
    (
        "vw_match_results",  # one readable row per match
        """
        CREATE VIEW vw_match_results AS
        SELECT m.match_id, m.match_date, m.match_desc, m.match_format, m.gender, m.status,
               t1.display_name AS team1, t2.display_name AS team2,
               v.venue_name, v.city, v.country AS venue_country,
               w.display_name AS winner, m.victory_margin, m.victory_type, m.result,
               s.series_name
        FROM matches m
        JOIN teams t1 ON t1.team_id = m.team1_id
        JOIN teams t2 ON t2.team_id = m.team2_id
        JOIN venues v ON v.venue_id = m.venue_id
        LEFT JOIN teams w ON w.team_id = m.winner_id
        LEFT JOIN series s ON s.series_id = m.series_id
        """,
    ),
    (
        "vw_player_batting_summary",  # per-player batting totals from match data
        """
        CREATE VIEW vw_player_batting_summary AS
        SELECT p.player_id, p.full_name, p.playing_role, p.gender, t.display_name AS team_name,
               COUNT(*) AS innings,
               SUM(b.runs) AS total_runs,
               ROUND(1.0 * SUM(b.runs) / NULLIF(SUM(CASE WHEN b.is_out THEN 1 ELSE 0 END), 0), 2) AS batting_avg,
               ROUND(100.0 * SUM(b.runs) / NULLIF(SUM(b.balls_faced), 0), 2) AS strike_rate,
               MAX(b.runs) AS highest_score
        FROM batting_performances b
        JOIN players p ON p.player_id = b.player_id
        JOIN teams t ON t.team_id = p.team_id
        GROUP BY p.player_id, p.full_name, p.playing_role, p.gender, t.display_name
        """,
    ),
]
