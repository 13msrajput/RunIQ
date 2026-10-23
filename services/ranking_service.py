"""ICC rankings from the Cricbuzz API, stored as snapshots in ``ranking_snapshots`` (offline fallback)."""
from __future__ import annotations

import pandas as pd  # tables
from sqlalchemy import delete, insert  # Core statements

from api.cricbuzz_client import CricbuzzClient  # API access
from models.schema import ranking_snapshots  # table
from services.api_parsers import parse_rankings  # JSON -> DataFrame
from utils.db_connection import get_connection, run_query  # DB helpers
from utils.exceptions import DatabaseError  # errors
from utils.logger import get_logger  # logging

logger = get_logger("rankings")  # module logger
CATEGORIES = {"Batting": "batsmen", "Bowling": "bowlers", "All-rounders": "allrounders", "Teams": "teams"}  # label -> API value
FORMATS = {"Test": "test", "ODI": "odi", "T20I": "t20"}  # label -> API value


def fetch_and_store(client: CricbuzzClient, category: str, fmt: str, women: bool) -> pd.DataFrame:
    """Call the API, keep the latest snapshot in the database and return the table."""
    frame = parse_rankings(client.get_rankings(category, fmt, women))
    gender = "female" if women else "male"
    if frame.empty:
        return frame
    rows = [{"category": category, "match_format": fmt, "gender": gender, "rank_pos": None if pd.isna(r.Rank) else int(r.Rank), "name": str(r.Name)[:120], "country": str(r.Country)[:80],
             "rating": None if pd.isna(r.Rating) else int(r.Rating), "points": None if pd.isna(r.Points) else int(r.Points)} for r in frame.itertuples()]
    try:
        with get_connection("saving rankings") as conn:  # replace the previous snapshot of the same list
            conn.execute(delete(ranking_snapshots).where((ranking_snapshots.c.category == category) & (ranking_snapshots.c.match_format == fmt) & (ranking_snapshots.c.gender == gender)))
            conn.execute(insert(ranking_snapshots), rows)
    except DatabaseError as exc:  # a storage problem must not hide the live data
        logger.warning("Could not store ranking snapshot: %s", exc.message)
    return frame


def latest_snapshot(category: str, fmt: str, women: bool) -> tuple[pd.DataFrame, str | None]:
    """Stored ranking list + the time it was fetched (``None`` when nothing is stored)."""
    df = run_query("""SELECT rank_pos AS "Rank", name AS "Name", country AS "Country", rating AS "Rating", points AS "Points", fetched_at
                      FROM ranking_snapshots WHERE category = :c AND match_format = :f AND gender = :g ORDER BY rank_pos""", {"c": category, "f": fmt, "g": "female" if women else "male"})
    if df.empty:
        return df, None
    return df.drop(columns=["fetched_at"]), str(df["fetched_at"].iloc[0])
