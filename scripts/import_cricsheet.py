"""CLI: download real match data from Cricsheet and load it into the database.

Examples
    python -m scripts.import_cricsheet                      # everything (Test, ODI, T20I - men and women)
    python -m scripts.import_cricsheet --since-year 2015    # smaller / faster
    python -m scripts.import_cricsheet --recent 7           # only matches added in the last 7 days (update)
    python -m scripts.import_cricsheet --zip tests_json.zip odis_json.zip t20s_json.zip   # files you downloaded yourself
"""

from __future__ import annotations

import argparse  # command-line options
import sys  # exit codes
from pathlib import Path

from models.constants import FORMATS  # Test / ODI / T20I
from services.cricsheet_importer import CricsheetImporter  # importer
from utils.db_connection import create_schema, reset_database  # schema helpers
from utils.exceptions import CricbuzzError  # our errors


def main() -> int:
    """Parse the options, run the import, print a summary."""
    parser = argparse.ArgumentParser(
        description="Import real international matches from Cricsheet (cricsheet.org)."
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=FORMATS,
        default=list(FORMATS),
        help="formats to import (default: all)",
    )
    parser.add_argument(
        "--gender",
        nargs="+",
        choices=["male", "female"],
        default=["male", "female"],
        help="men / women (default: both)",
    )
    parser.add_argument(
        "--since-year",
        type=int,
        default=None,
        help="only matches from this year onwards",
    )
    parser.add_argument(
        "--recent",
        type=int,
        choices=[2, 7, 30],
        default=None,
        help="only matches added in the last N days (quick update)",
    )
    parser.add_argument(
        "--zip",
        nargs="+",
        type=Path,
        default=None,
        help="use zip files you downloaded manually instead of downloading",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="import at most N matches (for a quick test)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="download the zip files again even if they are cached",
    )
    parser.add_argument(
        "--reset", action="store_true", help="DELETE all existing data first"
    )
    args = parser.parse_args()

    last = {"text": ""}

    def progress(done: int, total: int, message: str) -> None:
        """Print a progress line (only when the message changes or every 10 percent)."""
        line = f"{message} ({done}/{total})" if total > 1 else message
        if line != last["text"]:
            print("  " + line, flush=True)
            last["text"] = line

    try:
        reset_database() if args.reset else create_schema()
        importer = CricsheetImporter(
            formats=tuple(args.formats),
            genders=tuple(args.gender),
            since_year=args.since_year,
            limit=args.limit,
            progress=progress,
        )
        summary = importer.run(
            zips=args.zip, recent_days=args.recent, refresh=args.refresh
        )
    except CricbuzzError as exc:
        print(f"\nImport failed: {exc.message}\n{exc.details or ''}")
        return 1
    print(
        f"\nDone in {summary.seconds}s: imported {summary.imported}, already present {summary.skipped_existing}, filtered out {summary.skipped_filtered}, failed {summary.failed}."
    )
    print(
        f"Database now holds {summary.matches_total} matches and {summary.players_total} players."
    )
    for error in summary.errors[:5]:
        print("  problem:", error)
    print("Data: Cricsheet (cricsheet.org) - Open Data Commons Attribution License.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
