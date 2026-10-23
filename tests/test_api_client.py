"""API client tests using a fake HTTP session (no network needed)."""

from pathlib import Path

import pytest
import requests

from api import cricbuzz_client as module
from api.cricbuzz_client import CricbuzzClient
from config import Settings
from utils.exceptions import APIAuthError, APIError, APIRateLimitError


def make_settings(key="real-key"):
    return Settings(
        "sqlite://",
        key,
        "host",
        "https://host",
        5,
        0,
        0.0,
        "INFO",
        Path("."),
        Path("."),
    )


class FakeResponse:
    def __init__(self, status=200, payload=None, text="", bad_json=False):
        self.status_code, self._payload, self.text, self.bad_json, self.headers = (
            status,
            payload,
            text,
            bad_json,
            {},
        )

    def json(self):
        if self.bad_json:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    """Returns the queued responses one after another and remembers every request."""

    def __init__(self, *responses, error=None):
        self.responses, self.error, self.calls = list(responses), error, []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


@pytest.fixture(autouse=True)
def reset_route_memory():
    module._WORKING.clear()
    yield
    module._WORKING.clear()


def client_with(*responses, error=None, key="real-key"):
    return CricbuzzClient(make_settings(key), FakeSession(*responses, error=error))


def test_success_returns_json_and_sends_auth_headers():
    client = client_with(FakeResponse(payload={"ok": 1}))
    assert client.get_live_matches() == {"ok": 1}
    url, kwargs = client.session.calls[0]
    assert (
        url == "https://host/matches/v1/live"
        and kwargs["headers"]["X-RapidAPI-Key"] == "real-key"
    )


def test_missing_key_raises_auth_error_without_calling_network():
    client = client_with(FakeResponse(payload={}), key="")
    with pytest.raises(APIAuthError):
        client.get_live_matches()
    assert client.session.calls == []


@pytest.mark.parametrize(
    "status,exc",
    [
        (401, APIAuthError),
        (403, APIAuthError),
        (429, APIRateLimitError),
        (500, APIError),
    ],
)
def test_http_errors_are_mapped(status, exc):
    with pytest.raises(exc):
        client_with(FakeResponse(status=status)).get_rankings()


def test_invalid_json_timeout_and_connection_errors():
    with pytest.raises(APIError):
        client_with(FakeResponse(bad_json=True)).get_rankings()
    with pytest.raises(APIError):
        client_with(error=requests.exceptions.Timeout()).get_rankings()
    with pytest.raises(APIError):
        client_with(error=requests.exceptions.ConnectionError()).get_rankings()


def test_falls_back_to_the_next_route_on_404_and_remembers_it():
    client = client_with(FakeResponse(status=404), FakeResponse(payload={"matches": 1}))
    assert client.get_live_matches() == {
        "matches": 1
    }  # first route 404 -> second route works
    assert [c[0] for c in client.session.calls] == [
        "https://host/matches/v1/live",
        "https://host/matches/live",
    ]
    client.session.calls.clear()
    client.session.responses = [FakeResponse(payload={"again": 1})]
    client.get_live_matches()
    assert client.session.calls[0][0] == "https://host/matches/live"  # remembered


def test_all_routes_404_raises_api_error():
    with pytest.raises(APIError) as info:
        client_with(FakeResponse(status=404)).get_live_matches()
    assert info.value.status_code == 404


def test_placeholders_are_filled_and_query_params_sent():
    client = client_with(FakeResponse(payload={}))
    client.get_rankings("bowlers", "odi", True)
    url, kwargs = client.session.calls[0]
    assert url.endswith("/stats/v1/rankings/bowlers") and kwargs["params"] == {
        "formatType": "odi",
        "isWomen": "1",
    }
    client.get_scorecard(123)
    assert client.session.calls[1][0].endswith("/mcenter/v1/123/hscard")


def test_unknown_endpoint_and_missing_value():
    with pytest.raises(APIError):
        client_with(FakeResponse(payload={})).call("nope")
    with pytest.raises(APIError):
        client_with(FakeResponse(payload={})).call("scorecard")  # match_id missing


def test_player_search_passes_a_value_called_name():
    client = client_with(FakeResponse(payload={"player": []}))
    client.search_player("kohli")
    url, kwargs = client.session.calls[0]
    assert url.endswith("/stats/v1/player/search") and kwargs["params"] == {
        "plrN": "kohli"
    }
