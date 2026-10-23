"""Turn API matches and database rows into the dictionaries used by the match-card widgets (pure functions)."""

from __future__ import annotations

from services.api_parsers import LiveMatch  # API match dataclass

FORMAT_LABELS = {
    "TEST": "Test",
    "ODI": "ODI",
    "T20": "T20I",
    "T20I": "T20I",
}  # API value -> display label
NOT_LIVE_STATES = {
    "",
    "complete",
    "completed",
    "preview",
    "upcoming",
    "abandon",
    "abandoned",
    "no result",
    "cancelled",
}  # states that are not "in play"


def api_match_to_card(match: LiveMatch, force_live: bool = False) -> dict:
    """Card dictionary for a match returned by the Cricbuzz API."""
    state = (match.state or "").strip().lower()
    live = force_live or (state not in NOT_LIVE_STATES)
    when = f" · {match.start:%d %b %Y, %H:%M} UTC" if match.start else ""
    venue = ", ".join(part for part in (match.venue, match.city) if part)
    return {
        "top": " • ".join(
            part for part in (match.match_desc, match.series_name) if part
        )
        or "Match",
        "fmt": FORMAT_LABELS.get(
            (match.match_format or "").upper(), match.match_format or ""
        ),
        "team1": match.team1,
        "score1": "" if match.team1_score == "-" else match.team1_score,
        "team2": match.team2,
        "score2": "" if match.team2_score == "-" else match.team2_score,
        "status": match.status or match.state or "",
        "foot": (venue + when).strip(" ·"),
        "live": live,
        "ref": (
            {
                "src": "api",
                "id": match.match_id,
                "title": f"{match.team1} vs {match.team2}",
            }
            if match.match_id
            else None
        ),
    }


def group_by_series(matches: list[LiveMatch]) -> dict[str, list[LiveMatch]]:
    """Keep the API order but group matches under their series name."""
    groups: dict[str, list[LiveMatch]] = {}
    for match in matches:
        groups.setdefault(match.series_name or "Other matches", []).append(match)
    return groups


def filter_matches(matches: list[LiveMatch], scope: str) -> list[LiveMatch]:
    """'All', 'International', 'Women', 'League' or 'Domestic'."""
    if scope == "All":
        return matches
    if scope == "Women":
        return [m for m in matches if m.is_women]
    return [
        m for m in matches if m.match_type.lower() == scope.lower() and not m.is_women
    ]


def db_cards(df) -> list[dict]:
    """Cards for the database matches returned by ``catalog_service.list_matches``."""
    from services.catalog_service import (
        matches_to_cards,
    )  # local import keeps this module light

    cards = matches_to_cards(df)
    for card in cards:
        card["ref"] = {
            "src": "db",
            "id": card.pop("match_id"),
            "title": f"{card['team1']} vs {card['team2']}",
        }
    return cards
