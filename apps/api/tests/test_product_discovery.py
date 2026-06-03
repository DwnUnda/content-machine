"""Offline tests for Phase 5 web-search product discovery."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import ArticleJob, ArticleJobProduct, Product
from app.services.openai_client import OpenAIResponse
from app.services.product_research import discover_products_via_websearch

DISCOVERY_PAYLOAD = {
    "products": [
        {"name": "Ionmax ION632", "brand": "Ionmax", "model": "ION632", "category": "dehumidifier", "role": "Best Overall", "role_rationale": "Strong all-rounder.", "candidate_urls": [{"retailer": "Ionmax", "url": "https://ionmax.com.au/products/ion632"}], "why_recommended": "Great cool-climate performer."},
        {"name": "Ausclimate NWT Medium 20L", "brand": "Ausclimate", "model": "ACD220", "category": "dehumidifier", "role": "Best Budget", "role_rationale": "Cheapest capable unit.", "candidate_urls": [{"retailer": "Ausclimate", "url": "https://ausclimate.com.au/products/acd220"}], "why_recommended": "Good value."},
        {"name": "DeLonghi Tasciugo 25L", "brand": "DeLonghi", "model": "DDSX225", "category": "dehumidifier", "role": "Best for Large Homes", "role_rationale": "High extraction.", "candidate_urls": [{"retailer": "The Good Guys", "url": "https://thegoodguys.com.au/delonghi-ddsx225"}], "why_recommended": "Big capacity."},
        {"name": "Breville All Climate", "brand": "Breville", "model": "LAD358", "category": "dehumidifier", "role": "Best 2-in-1", "role_rationale": "Purifier combo.", "candidate_urls": [{"retailer": "JB Hi-Fi", "url": "https://jbhifi.com.au/breville-lad358"}], "why_recommended": "Dehumidifier + purifier."},
        {"name": "Ausclimate Compact 10L", "brand": "Ausclimate", "model": "ACD210", "category": "dehumidifier", "role": "Best for Small Spaces", "role_rationale": "Compact.", "candidate_urls": [{"retailer": "Ausclimate", "url": "https://ausclimate.com.au/products/acd210"}], "why_recommended": "Small and quiet."},
    ],
    "roles_chosen": ["Best Overall", "Best Budget", "Best for Large Homes", "Best 2-in-1", "Best for Small Spaces"],
    "notes": "Spread across price and capacity.",
}


def _patch_discovery(monkeypatch, payload=DISCOVERY_PAYLOAD):
    def fake(self, *, instructions, input_text, model=None, max_output_tokens=6000, web_search_tool_type="web_search"):  # noqa: ANN001, ANN002
        return OpenAIResponse(model="gpt-5.5", content_text="{}", response_json={"output": [{"type": "web_search_call"}]}, parsed_json=payload)

    monkeypatch.setattr("app.services.openai_client.OpenAIClient.generate_json_with_web_search", fake)


def _make_job(post_type: str = "money_post") -> int:
    client = TestClient(app)
    return client.post(
        "/api/article-jobs",
        json={"title": "Best dehumidifiers for mould", "primary_keyword": "best dehumidifier australia", "post_type": post_type},
    ).json()["id"]


def test_discovery_creates_links_with_roles(monkeypatch):
    _patch_discovery(monkeypatch)
    job_id = _make_job()
    db = SessionLocal()
    try:
        job = db.get(ArticleJob, job_id)
        links = discover_products_via_websearch(db, job, max_products=5)
        assert len(links) == 5
        roles = {link.product.role for link in links}
        assert roles == {"Best Overall", "Best Budget", "Best for Large Homes", "Best 2-in-1", "Best for Small Spaces"}
        for link in links:
            assert link.extraction_status == "research_needed"
            assert link.source_type == "discovered"
            assert link.raw_extracted_json["discovered"] is True
            assert link.raw_extracted_json["role"] == link.product.role
            assert link.product.product_url  # a candidate URL was stored as the starting point
    finally:
        db.close()


def test_discovery_respects_max_products(monkeypatch):
    _patch_discovery(monkeypatch)
    job_id = _make_job()
    db = SessionLocal()
    try:
        job = db.get(ArticleJob, job_id)
        links = discover_products_via_websearch(db, job, max_products=3)
        assert len(links) == 3
    finally:
        db.close()


def test_discovery_skips_already_linked_products(monkeypatch):
    _patch_discovery(monkeypatch)
    job_id = _make_job()
    db = SessionLocal()
    try:
        # Pre-link one of the products the discovery will return.
        product = Product(name="Ionmax ION632", brand="Ionmax", category="dehumidifier", extraction_status="success")
        db.add(product)
        db.commit()
        db.refresh(product)
        db.add(ArticleJobProduct(article_job_id=job_id, product_id=product.id, source_url="https://x", source_type="retailer", extraction_status="success"))
        db.commit()

        job = db.get(ArticleJob, job_id)
        links = discover_products_via_websearch(db, job, max_products=5)
        # 5 returned by the model, but the pre-linked Ionmax is skipped -> 4 created.
        assert len(links) == 4
        assert all(link.product.name != "Ionmax ION632" for link in links)
    finally:
        db.close()
