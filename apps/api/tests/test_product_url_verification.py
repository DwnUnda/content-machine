"""Offline tests for the URL verification utility (Phase 3).

httpx is monkeypatched so no real network calls are made.
"""
from __future__ import annotations

import httpx
import pytest

from app.services import product_research as pr

_FILLER = " ".join(["This Australian retailer page describes the appliance in detail."] * 8)
ION_HTML = (
    "<html><head><title>Ionmax ION632 10L Desiccant Dehumidifier - Ionmax</title></head>"
    "<body><h1>Ionmax ION632</h1><p>10L/day desiccant dehumidifier with a 3.5L tank, "
    f"continuous drainage and a built-in air filter. {_FILLER}</p></body></html>"
)
# A generic / soft-404 page: long enough to pass the length check, but never mentions ION632 or Ionmax.
GENERIC_HTML = (
    "<html><head><title>Winning Appliances | Kitchen &amp; Laundry</title></head>"
    f"<body><p>Browse our full range of kitchen and laundry appliances. {_FILLER}</p></body></html>"
)
BOT_WALL_HTML = "<html><head><title>Pardon our interruption</title></head><body>As you were browsing something about your browser made us think you were a bot. Please verify you are a human.</body></html>"


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeClient:
    """Stands in for httpx.Client; returns canned responses keyed by URL."""

    routes: dict[str, object] = {}

    def __init__(self, *args, **kwargs) -> None:  # noqa: D401, ANN002, ANN003
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        return None

    def get(self, url: str):  # noqa: ANN201
        outcome = self.routes[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture(autouse=True)
def _patch_httpx(monkeypatch):
    monkeypatch.setattr(pr.httpx, "Client", _FakeClient)
    _FakeClient.routes = {}
    yield


def test_verified_when_live_and_model_matches():
    url = "https://ionmax.com.au/products/ionmax-ion632"
    _FakeClient.routes = {url: _FakeResponse(200, ION_HTML)}
    result = pr.verify_product_url(url, brand="Ionmax", model="ION632", name="Ionmax ION632")
    assert result["verification"] == pr.VERIFY_VERIFIED
    assert result["matched"] is True
    assert result["status"] == 200


def test_dead_on_404_is_rejected():
    url = "https://www.jbhifi.com.au/products/ionmax-ion632-wrong"
    _FakeClient.routes = {url: _FakeResponse(404, "")}
    result = pr.verify_product_url(url, brand="Ionmax", model="ION632", name="Ionmax ION632")
    assert result["verification"] == pr.VERIFY_DEAD
    assert pr.url_is_dead(result) is True


def test_403_is_kept_as_blocked_not_dead():
    """The Big W case: anti-bot 403 must not be rejected."""
    url = "https://www.bigw.com.au/product/ionmax-ion632/p/123"
    _FakeClient.routes = {url: _FakeResponse(403, "")}
    result = pr.verify_product_url(url, brand="Ionmax", model="ION632", name="Ionmax ION632")
    assert result["verification"] == pr.VERIFY_BLOCKED
    assert pr.url_is_dead(result) is False


def test_js_bot_wall_detected_as_blocked():
    url = "https://www.appliancesonline.com.au/product/ion632/"
    _FakeClient.routes = {url: _FakeResponse(200, BOT_WALL_HTML)}
    result = pr.verify_product_url(url, brand="Ionmax", model="ION632", name="Ionmax ION632")
    assert result["verification"] == pr.VERIFY_BLOCKED


def test_live_but_no_product_match_is_unverified():
    url = "https://www.winnings.com.au/p/ionmax-dehumidifier-ion632"
    _FakeClient.routes = {url: _FakeResponse(200, GENERIC_HTML)}
    result = pr.verify_product_url(url, brand="Ionmax", model="ION632", name="Ionmax ION632")
    assert result["verification"] == pr.VERIFY_UNVERIFIED
    assert result["matched"] is False


def test_connection_error_is_error_not_dead():
    url = "https://unreachable.example.com/x"
    _FakeClient.routes = {url: httpx.ConnectError("boom")}
    result = pr.verify_product_url(url, brand="Ionmax", model="ION632", name="Ionmax ION632")
    assert result["verification"] == pr.VERIFY_ERROR
    assert pr.url_is_dead(result) is False


def test_verify_list_dedupes_and_summarises():
    live = "https://ionmax.com.au/products/ionmax-ion632"
    dead = "https://www.jbhifi.com.au/wrong"
    _FakeClient.routes = {live: _FakeResponse(200, ION_HTML), dead: _FakeResponse(404, "")}
    results = pr.verify_product_urls([live, live, dead], brand="Ionmax", model="ION632", name="Ionmax ION632")
    assert len(results) == 2  # deduped
    assert pr.has_publishable_url(results) is True
    assert [r for r in results if pr.url_is_dead(r)][0]["url"] == dead
