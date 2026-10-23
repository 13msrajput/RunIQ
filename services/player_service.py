"""CRUD for ``players`` (validated)."""
from __future__ import annotations

from datetime import date  # earliest allowed birth date

from models.constants import BATTING_STYLES, BOWLING_STYLES, GENDERS, ROLES  # allowed values
from models.schema import players  # table
from services.base_crud_service import BaseCrudService  # shared engine
from utils.db_connection import run_scalar  # lookups
from utils.validators import require_text, validate_bool, validate_choice, validate_date, validate_int  # validators


class PlayerService(BaseCrudService):
    """Create / read / update / delete players."""

    entity_name = "player"
    table = players
    pk_columns = ("player_id",)
    required_on_create = ("full_name", "team_id", "playing_role")
    rules = {
        "full_name": lambda v: require_text(v, "Full name", min_length=2, max_length=100),
        "team_id": lambda v: validate_int(v, "Team", minimum=1),
        "gender": lambda v: validate_choice(v, "Gender", GENDERS),
        "playing_role": lambda v: validate_choice(v, "Playing role", ROLES),
        "batting_style": lambda v: validate_choice(v, "Batting style", BATTING_STYLES, required=False),
        "bowling_style": lambda v: validate_choice(v, "Bowling style", BOWLING_STYLES, required=False),
        "date_of_birth": lambda v: validate_date(v, "Date of birth", required=False, not_in_future=True, minimum=date(1930, 1, 1)),
        "is_active": lambda v: validate_bool(v, "Active flag"),
        "api_player_id": lambda v: validate_int(v, "Cricbuzz player id", minimum=1, required=False),
    }

    def create(self, data):  # noqa: D102 - the gender follows the team when it is not given
        data = dict(data)
        if not data.get("gender") and data.get("team_id"):
            data["gender"] = run_scalar("SELECT gender FROM teams WHERE team_id = :t", {"t": int(data["team_id"])}) or "male"
        return super().create(data)
