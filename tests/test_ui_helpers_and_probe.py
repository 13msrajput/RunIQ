"""Theme / card helpers, branding and the API probe."""

import base64
import io

from PIL import Image

from services.api_parsers import parse_matches_response
from services.api_probe import probe
from services.card_builders import api_match_to_card, filter_matches, group_by_series
from tests.fake_api import FakeApi, RESPONSES
from utils import branding, icons, theme
from tests.test_api_parsers import MATCHES


def test_palettes_pages_and_icons():
    assert theme.DARK.keys() == theme.LIGHT.keys()
    assert theme.apply_theme and all(
        len(p) == 3 and p[2].startswith(":material/")
        for p in theme.PAGES + theme.MORE_PAGES
    )
    assert (
        icons.icon("home").startswith("<svg")
        and icons.icon("does-not-exist") == ""
        and len(icons.ICON_NAMES) >= 30
    )


def test_escaping_headers_and_initials():
    assert (
        theme.esc("<script>x</script>") == "&lt;script&gt;x&lt;/script&gt;"
        and theme.esc(None) == ""
    )
    card = theme.match_card_html(
        {
            "top": "<b>x</b>",
            "fmt": "ODI",
            "team1": "A",
            "team2": "B",
            "status": "ok",
            "foot": "f",
            "winner": 1,
        }
    )
    assert "<b>x</b>" not in card and "dim" in card and "ODI" in card
    live = theme.match_card_html(
        {"top": "t", "team1": "A", "team2": "B", "status": "In play", "live": True}
    )
    assert "cb-live" in live and "cb-status live" in live
    assert [
        theme._nice_header(h)
        for h in ("avg_runs", "sr", "Batter", "100s", "hs", "win_pct")
    ] == ["Avg runs", "SR", "Batter", "100s", "HS", "Win pct"]
    assert theme.initials("V Kohli") == "VK" and theme.initials("") == "?"


def test_logo_is_embedded_and_valid():
    for size, expected in (("small", 96), ("medium", 192), ("large", 320)):
        uri = branding.logo_data_uri(size)
        assert uri.startswith("data:image/png;base64,")
        assert Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).size == (
            expected,
            expected,
        )
    assert branding.APP_NAME == "RunIQ" and branding.logo_image("small").mode == "RGBA"


def test_card_builders_and_filters():
    matches = parse_matches_response(MATCHES)
    card = api_match_to_card(matches[0])
    assert card["fmt"] == "T20I" and card["score1"] == "118/5 (7.4)"
    assert (
        card["score2"] == ""
        and card["ref"]["src"] == "api"
        and card["ref"]["id"] == 1001
        and card["foot"].startswith("M.Chinnaswamy")
    )
    assert (
        api_match_to_card(matches[0], force_live=True)["live"] is True
        and api_match_to_card(matches[0])["live"] is False
    )  # "Complete" state
    assert [m.match_id for m in filter_matches(matches, "Women")] == [2002]
    assert [m.match_id for m in filter_matches(matches, "International")] == [
        1001
    ] and len(filter_matches(matches, "All")) == 2
    assert list(group_by_series(matches)) == ["WI tour of India", "W series"]


def test_probe_reports_every_endpoint_ok_with_a_healthy_api():
    rows = probe(FakeApi())
    assert len(rows) == 21 and all(r["Result"] == "OK" for r in rows), [
        r for r in rows if r["Result"] != "OK"
    ]


def test_probe_skips_dependent_endpoints_when_samples_are_missing():
    class Sparse(FakeApi):
        def call(self, endpoint, /, **values):
            return (
                {}
                if endpoint
                in ("recent", "series_list", "teams_list", "player_search", "news_list")
                else RESPONSES[endpoint]
            )

    rows = {r["Feature"]: r["Result"] for r in probe(Sparse())}
    assert (
        rows["Scorecard"] == "SKIPPED"
        and rows["Series matches"] == "SKIPPED"
        and rows["Team players"] == "SKIPPED"
        and rows["Player profile"] == "SKIPPED"
        and rows["News story"] == "SKIPPED"
    )
