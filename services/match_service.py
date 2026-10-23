"""CRUD for ``matches`` with cross-field business rules."""
from __future__ import annotations

from datetime import date  # date type

from models.constants import FORMATS, GENDERS, MATCH_STATUSES, RESULT_TYPES, TOSS_DECISIONS, VICTORY_TYPES  # allowed values
from models.schema import matches  # table
from services.base_crud_service import BaseCrudService  # shared engine
from utils.db_connection import run_query  # lookups
from utils.exceptions import ValidationError  # business-rule errors
from utils.validators import require_text, validate_choice, validate_date, validate_int  # validators


class MatchService(BaseCrudService):
    """Create / read / update / delete matches."""

    entity_name = "match"
    table = matches
    pk_columns = ("match_id",)
    required_on_create = ("match_desc", "match_format", "team1_id", "team2_id", "venue_id", "match_date")
    rules = {
        "series_id": lambda v: validate_int(v, "Series", minimum=1, required=False),
        "match_desc": lambda v: require_text(v, "Match description", min_length=3, max_length=100),
        "match_format": lambda v: validate_choice(v, "Format", FORMATS),
        "gender": lambda v: validate_choice(v, "Gender", GENDERS),
        "team1_id": lambda v: validate_int(v, "Team 1", minimum=1),
        "team2_id": lambda v: validate_int(v, "Team 2", minimum=1),
        "venue_id": lambda v: validate_int(v, "Venue", minimum=1),
        "match_date": lambda v: validate_date(v, "Match date", minimum=date(1970, 1, 1)),
        "status": lambda v: validate_choice(v, "Status", MATCH_STATUSES),
        "toss_winner_id": lambda v: validate_int(v, "Toss winner", minimum=1, required=False),
        "toss_decision": lambda v: validate_choice(v, "Toss decision", TOSS_DECISIONS, required=False),
        "winner_id": lambda v: validate_int(v, "Winner", minimum=1, required=False),
        "victory_margin": lambda v: validate_int(v, "Victory margin", minimum=0, maximum=1000, required=False),
        "victory_type": lambda v: validate_choice(v, "Victory type", VICTORY_TYPES, required=False),
        "result": lambda v: validate_choice(v, "Result", RESULT_TYPES),
        "source": lambda v: validate_choice(v, "Source", ("cricsheet", "api", "manual")),
    }

    def create(self, data):  # noqa: D102 - fills defaults then delegates
        data = {"status": "Upcoming", "source": "manual", "result": "normal", **data}
        if not data.get("gender") and data.get("team1_id"):  # the gender follows the teams
            found = run_query("SELECT gender FROM teams WHERE team_id = :t", {"t": int(data["team1_id"])})
            data["gender"] = found.iloc[0, 0] if not found.empty else "male"
        return super().create(data)

    def cross_validate(self, merged: dict) -> None:
        """Business rules that involve several columns."""
        team1, team2 = merged.get("team1_id"), merged.get("team2_id")
        if team1 is not None and team1 == team2:
            raise ValidationError("Team 1 and Team 2 must be different.")
        if team1 and team2:
            genders = run_query("SELECT DISTINCT gender FROM teams WHERE team_id IN (:a, :b)", {"a": int(team1), "b": int(team2)})
            if len(genders) > 1:
                raise ValidationError("A match cannot be between a men's and a women's team.")
        for label, key in (("Toss winner", "toss_winner_id"), ("Winner", "winner_id")):
            value = merged.get(key)
            if value is not None and value not in (team1, team2):
                raise ValidationError(f"{label} must be one of the two playing teams.")
        if bool(merged.get("toss_winner_id")) != bool(merged.get("toss_decision")):
            raise ValidationError("Toss winner and toss decision must be given together.")
        has_result = [merged.get("winner_id"), merged.get("victory_margin"), merged.get("victory_type")]
        if merged.get("status") != "Completed" and any(x is not None for x in has_result):
            raise ValidationError("Only completed matches can have a winner or victory margin.")
        if merged.get("victory_type") in ("runs", "wickets", "innings") and merged.get("victory_margin") is None:
            raise ValidationError("A victory by runs / wickets / innings needs a margin.")
        if merged.get("winner_id") is None and merged.get("victory_type") is not None:
            raise ValidationError("A victory type needs a winner.")

    def derived_fields(self, merged: dict) -> dict:
        """match_year and match_quarter always follow match_date."""
        match_date = merged["match_date"]
        return {"match_year": match_date.year, "match_quarter": (match_date.month - 1) // 3 + 1}
