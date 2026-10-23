"""CLI: check that your RapidAPI key is loaded and every Cricbuzz endpoint RunIQ uses answers.

Usage:  python -m scripts.check_api
Prints a table (OK / FAILED / SKIPPED) and never shows your full key.
"""

from __future__ import annotations

import sys  # exit codes

from api.cricbuzz_client import CricbuzzClient  # API client
from config import BASE_DIR, get_settings  # settings
from services.api_probe import probe  # endpoint tests


def mask(key: str) -> str:
    """abcd...wxyz so the secret is never printed in full."""
    return (
        "(empty)"
        if not key
        else (key[:4] + "..." + key[-4:] if len(key) > 8 else "****")
    )


def main() -> int:
    """Run the checks; return 0 when everything works."""
    settings = get_settings()
    print("=== Step 1: configuration ===")
    print(f".env file found : {(BASE_DIR / '.env').exists()}  ({BASE_DIR / '.env'})")
    print(
        f"API key loaded  : {settings.has_api_key}  ->  {mask(settings.rapidapi_key)}  (length {len(settings.rapidapi_key)})"
    )
    print(f"API host        : {settings.rapidapi_host}")
    if not settings.has_api_key:
        print(
            "\nFAILED: no real key found. Put RAPIDAPI_KEY=... in the .env file next to main.py and run again."
        )
        return 1
    print("\n=== Step 2: live API calls (about 20 requests) ===")
    rows = probe(
        CricbuzzClient(settings),
        progress=lambda fraction, label: print(f"  ...{label}"),
    )
    print()
    failed = 0
    for row in rows:
        mark = (
            "OK     "
            if row["Result"] == "OK"
            else "SKIPPED" if row["Result"] == "SKIPPED" else "FAILED "
        )
        failed += mark.strip() == "FAILED"
        print(f"{mark} {row['Feature']:<22} {row['Result']:<18} {row['Details']}")
    print(
        "\nRESULT:",
        (
            "ALL ENDPOINTS WORK"
            if failed == 0
            else f"{failed} endpoint(s) failed - send this output to get the paths fixed (api/endpoints.py)"
        ),
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
