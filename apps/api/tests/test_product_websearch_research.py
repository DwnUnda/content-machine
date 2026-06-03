"""Offline integration test for Phase 4 web-search product research.

Both the OpenAI web-search call and the URL-verification httpx calls are
monkeypatched, so the whole route -> research -> verify -> auto-approve path
runs with no network access.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import product_research as pr
from app.services.openai_client import OpenAIResponse

_FILLER = " ".join(["This Australian retailer page describes the dehumidifier in detail."] * 8)
ION_HTML = (
    "<html><head><title>Ionmax ION632 10L Desiccant Dehumidifier - Ionmax</title></head>"
    f"<body><h1>Ionmax ION632</h1><p>10L/day desiccant dehumidifier. {_FILLER}</p></body></html>"
)

# What the (faked) model returns: a full card with one good URL and one dead URL.
FAKE_CARD = {
    "product_name": "Ionmax ION632 10L Desiccant Dehumidifier",
    "brand": "Ionmax",
    "model": "ION632",
    "category": "dehumidifier",
    "manufacturer_url": "https://ionmax.com.au/products/ionmax-ion632",
    "retailer_urls": [
        {"retailer": "Ionmax", "url": "https://ionmax.com.au/products/ionmax-ion632", "price_aud": "A$399", "as_of": "2026-05-30"},
        {"retailer": "JB Hi-Fi", "url": "https://www.jbhifi.com.au/wrong", "price_aud": "A$420", "as_of": "2026-05-30"},
    ],
    "price_range_text": "A$399–A$475 across AU retailers",
    "capacity_text": "10L/day",
    "tank_size_text": "3.5L",
    "best_for": "Cool, damp rooms and winter condensation",
    "who_should_buy": "People in cool damp homes",
    "common_positives": ["Great in cold weather", "Good for condensation"],
    "common_complaints": ["Can be noisy on high"],
    "key_specs": ["10L/day moisture removal", "3.5L tank"],
    "bottom_line": "Solid cool-climate pick.",
    "warranty_text": "Not confirmed",
    "confidence": "Medium",
}


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeClient:
    routes: dict[str, object] = {}

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        return None

    def get(self, url: str):  # noqa: ANN201
        if url not in self.routes:
            return _FakeResponse(404, "")
        return self.routes[url]


@pytest.fixture
def patched(monkeypatch):
    # Force the route down the web-search branch regardless of real .env.
    monkeypatch.setattr(
        "app.api.routes.article_jobs.get_settings",
        lambda: SimpleNamespace(openai_api_key="test-key"),
    )

    def fake_web_search(self, *, instructions, input_text, model=None, max_output_tokens=6000, web_search_tool_type="web_search"):  # noqa: ANN001, ANN002
        return OpenAIResponse(
            model="gpt-5.5",
            content_text="{}",
            response_json={"output": [{"type": "web_search_call"}, {"type": "message"}]},
            parsed_json=FAKE_CARD,
        )

    monkeypatch.setattr(
        "app.services.openai_client.OpenAIClient.generate_json_with_web_search",
        fake_web_search,
    )

    _FakeClient.routes = {
        "https://ionmax.com.au/products/ionmax-ion632": _FakeResponse(200, ION_HTML),
        "https://www.jbhifi.com.au/wrong": _FakeResponse(404, ""),
    }
    monkeypatch.setattr(pr.httpx, "Client", _FakeClient)
    yield


def test_websearch_research_fills_card_verifies_urls_and_auto_approves(patched):
    client = TestClient(app)
    article = client.post(
        "/api/article-jobs",
        json={"title": "Best dehumidifiers", "primary_keyword": "best dehumidifier australia", "post_type": "money_post"},
    ).json()
    source = client.post(
        f"/api/article-jobs/{article['id']}/product-sources",
        json={"source_url": "https://www.appliancesonline.com.au/product/andatech-dehumidifier-ionmax-ion632/", "source_type": "retailer"},
    ).json()

    resp = client.post(f"/api/article-jobs/{article['id']}/products/{source['id']}/research-card")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Auto-approved because core fields are present AND a URL verified live.
    assert body["draft_ready"] is True
    assert body["draft_ready_approved"] is True

    product = body["product"]
    assert product["capacity_text"] == "10L/day"
    assert product["best_for"].startswith("Cool")
    # Dead JB Hi-Fi URL dropped; only the verified Ionmax URL kept, with its price.
    retailer_urls = product["retailer_urls"]
    assert len(retailer_urls) == 1
    assert retailer_urls[0]["url"] == "https://ionmax.com.au/products/ionmax-ion632"
    assert retailer_urls[0]["price_aud"] == "A$399"
    assert retailer_urls[0]["verification"] == pr.VERIFY_VERIFIED

    # The dead URL is recorded in the verification audit trail.
    verdicts = body["raw_extracted_json"]["url_verifications"]
    dead = [v for v in verdicts if v["verification"] == pr.VERIFY_DEAD]
    assert any("jbhifi" in v["url"] for v in dead)


def test_websearch_research_holds_for_review_when_core_field_missing(patched, monkeypatch):
    # Drop best_for so a blocking field is missing -> must NOT auto-approve.
    card = {**FAKE_CARD, "best_for": "Not confirmed"}

    def fake_web_search(self, *, instructions, input_text, model=None, max_output_tokens=6000, web_search_tool_type="web_search"):  # noqa: ANN001, ANN002
        return OpenAIResponse(model="gpt-5.5", content_text="{}", response_json={"output": []}, parsed_json=card)

    monkeypatch.setattr(
        "app.services.openai_client.OpenAIClient.generate_json_with_web_search",
        fake_web_search,
    )

    client = TestClient(app)
    article = client.post(
        "/api/article-jobs",
        json={"title": "Best dehumidifiers", "primary_keyword": "best dehumidifier", "post_type": "money_post"},
    ).json()
    source = client.post(
        f"/api/article-jobs/{article['id']}/product-sources",
        json={"source_url": "https://www.appliancesonline.com.au/product/andatech-dehumidifier-ionmax-ion632/", "source_type": "retailer"},
    ).json()
    resp = client.post(f"/api/article-jobs/{article['id']}/products/{source['id']}/research-card")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["draft_ready"] is False
    assert body["extraction_status"] == "researched_needs_review"
    assert "missing best for" in body["missing_fields"]
