"""CRUD for ``player_career_stats`` (composite key: player_id + match_format)."""

from __future__ import annotations

import pandas as pd  # tables

from models.constants import FORMATS  # allowed formats
from models.schema import player_career_stats  # table
from services.base_crud_service import BaseCrudService  # shared engine
from utils.db_connection import run_query  # SQL -> DataFrame
from utils.exceptions import ValidationError  # business-rule errors
from utils.validators import validate_choice, validate_float, validate_int  # validators

_int = lambda label: (
    lambda v: validate_int(v, label, minimum=0, maximum=100000)
)  # noqa: E731
_float = lambda label, required=True: (
    lambda v: validate_float(v, label, minimum=0, maximum=1000, required=required)
)  # noqa: E731


class CareerStatsService(BaseCrudService):
    """Create / read / update / delete a player's career numbers for one format."""

    entity_name = "career stat row"
    table = player_career_stats
    pk_columns = ("player_id", "match_format")
    required_on_create = ("player_id", "match_format", "matches")
    rules = {
        "player_id": lambda v: validate_int(v, "Player", minimum=1),
        "match_format": lambda v: validate_choice(v, "Format", FORMATS),
        "matches": _int("Matches"),
        "innings": _int("Innings"),
        "not_outs": _int("Not outs"),
        "runs": lambda v: validate_int(v, "Runs", minimum=0, maximum=100000),
        "balls_faced": lambda v: validate_int(
            v, "Balls faced", minimum=0, maximum=1000000
        ),
        "highest_score": lambda v: validate_int(
            v, "Highest score", minimum=0, maximum=600
        ),
        "batting_avg": _float("Batting average"),
        "strike_rate": _float("Strike rate"),
        "centuries": _int("Centuries"),
        "fifties": _int("Fifties"),
        "wickets": _int("Wickets"),
        "bowling_avg": _float("Bowling average", required=False),
        "economy": lambda v: validate_float(
            v, "Economy", minimum=0, maximum=36, required=False
        ),
        "catches": _int("Catches"),
        "stumpings": _int("Stumpings"),
    }

    def cross_validate(self, merged: dict) -> None:
        """Rules that involve several columns."""
        if (merged.get("not_outs") or 0) > (merged.get("innings") or 0):
            raise ValidationError("Not outs cannot be more than innings.")
        if (merged.get("highest_score") or 0) > (merged.get("runs") or 0):
            raise ValidationError("Highest score cannot be more than total runs.")
        if (merged.get("innings") or 0) > (merged.get("matches") or 0):
            raise ValidationError("Innings cannot be more than matches.")

    def with_player_names(
        self, player_id: int | None = None, limit: int = 500
    ) -> pd.DataFrame:
        """Career rows joined with the player name."""
        sql = "SELECT cs.*, p.full_name FROM player_career_stats cs JOIN players p ON p.player_id = cs.player_id WHERE 1 = 1"
        params: dict = {"limit": int(limit)}
        if player_id:
            sql += " AND cs.player_id = :player_id"
            params["player_id"] = int(player_id)
        sql += " ORDER BY p.full_name, cs.match_format LIMIT :limit"
        return run_query(sql, params)
