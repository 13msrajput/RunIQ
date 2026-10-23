"""Shared constants (allowed values) used by the schema, validators and UI."""

from __future__ import annotations

ROLES = (
    "Batsman",
    "Bowler",
    "All-rounder",
    "Wicket-keeper",
)  # playing roles (derived from match data)
FORMATS = ("Test", "ODI", "T20I")  # official international formats
GENDERS = ("male", "female")  # Cricsheet gender values
GENDER_LABEL = {"male": "Men", "female": "Women"}  # labels shown in the UI
BATTING_STYLES = ("Right-hand bat", "Left-hand bat")  # batting hand
BOWLING_STYLES = (  # bowling styles
    "Right-arm fast",
    "Right-arm fast-medium",
    "Right-arm medium",
    "Left-arm fast",
    "Left-arm medium",
    "Right-arm off-break",
    "Right-arm leg-break",
    "Left-arm orthodox",
    "Left-arm wrist-spin",
)
MATCH_STATUSES = ("Upcoming", "Live", "Completed")  # lifecycle of a match
TOSS_DECISIONS = ("bat", "bowl")  # what the toss winner chose
VICTORY_TYPES = (
    "runs",
    "wickets",
    "innings",
    "super_over",
    "bowl_out",
)  # how a match was won
RESULT_TYPES = ("normal", "tie", "no result", "draw")  # overall result
