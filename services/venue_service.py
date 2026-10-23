"""CRUD for ``venues`` (e.g. to correct a country or capacity)."""
from __future__ import annotations

from models.schema import venues  # table
from services.base_crud_service import BaseCrudService  # shared engine
from utils.validators import optional_text, require_text, validate_int  # validators


class VenueService(BaseCrudService):
    """Create / read / update / delete venues."""

    entity_name = "venue"
    table = venues
    pk_columns = ("venue_id",)
    required_on_create = ("venue_name", "city")
    rules = {
        "venue_name": lambda v: require_text(v, "Venue name", min_length=2, max_length=160),
        "city": lambda v: require_text(v, "City", min_length=2, max_length=80),
        "country": lambda v: optional_text(v, "Country", max_length=80),
        "capacity": lambda v: validate_int(v, "Capacity", minimum=1, maximum=300000, required=False),
        "api_venue_id": lambda v: validate_int(v, "Cricbuzz venue id", minimum=1, required=False),
    }
