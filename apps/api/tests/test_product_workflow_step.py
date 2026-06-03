"""Offline tests for Phase 6: the automatic product_research workflow step."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import ArticleJob, ArticleJobProduct, Product
from app.services import product_research as pr
from app.services import workflow as wf


def _make_job(post_type: str) -> int:
    client = TestClient(app)
    return client.post(
        "/api/article-jobs",
        json={"title": "Best dehumidifiers", "primary_keyword": "best dehumidifier australia", "post_type": post_type},
    ).json()["id"]


def _fake_discover(n: int):
    def discover(db, job, *, max_products=5):  # noqa: ANN001
        links = []
        for i in range(min(n, max_products)):
            product = Product(name=f"Disco Product {i}", brand=f"Brand{i}", category="dehumidifier", role=f"Role {i}", extraction_status="research_needed")
            db.add(product)
            db.commit()
            db.refresh(product)
            link = ArticleJobProduct(article_job_id=job.id, product_id=product.id, source_url=f"https://x/{i}", source_type="discovered", extraction_status="research_needed", raw_extracted_json={"discovered": True})
            db.add(link)
            db.commit()
            db.refresh(link)
            links.append(link)
        return links

    return discover


def _fake_research_makes_ready(db, link, *, current_date=None, auto_approve=True):  # noqa: ANN001
    """Fill the 4 core fields and approve, so the card becomes draft-ready."""
    product = link.product
    product.best_for = "Cool damp rooms"
    product.common_complaints = "Can be noisy"
    if not product.brand:
        product.brand = "BrandX"
    product.extraction_status = "researched_needs_review"
    db.add(product)
    link.extraction_status = "researched_needs_review"
    db.add(link)
    db.commit()
    pr.approve_product_draft_ready(db, link)
    return link


def test_run_product_research_noop_for_non_gated(monkeypatch):
    monkeypatch.setattr(wf, "get_settings", lambda: SimpleNamespace(openai_api_key="x"))
    job_id = _make_job("informational_blog")
    db = SessionLocal()
    try:
        job = db.get(ArticleJob, job_id)
        result = wf.run_product_research(db, job)
        assert "not required" in result["message"].lower()
    finally:
        db.close()


def test_run_product_research_discovers_and_makes_cards_ready(monkeypatch):
    monkeypatch.setattr(wf, "get_settings", lambda: SimpleNamespace(openai_api_key="x"))
    monkeypatch.setattr(pr, "discover_products_via_websearch", _fake_discover(3))
    monkeypatch.setattr(pr, "research_product_via_websearch", _fake_research_makes_ready)

    job_id = _make_job("money_post")
    db = SessionLocal()
    try:
        job = db.get(ArticleJob, job_id)
        # No URLs entered -> discovery path.
        result = wf.run_product_research(db, job)
        assert "Discovered 3" in result["message"]
        assert wf._draft_ready_count(job) == 3

        # Workflow state should now report the product step complete.
        state = wf.get_workflow_state(db, job)
        steps = {s["step_key"]: s for s in state["steps"]}
        assert "product_research" in steps
        assert steps["product_research"]["status"] == "complete"
    finally:
        db.close()


def test_run_product_research_researches_existing_urls_without_discovery(monkeypatch):
    monkeypatch.setattr(wf, "get_settings", lambda: SimpleNamespace(openai_api_key="x"))

    discover_called = {"n": 0}

    def discover_spy(db, job, *, max_products=5):  # noqa: ANN001
        discover_called["n"] += 1
        return []

    monkeypatch.setattr(pr, "discover_products_via_websearch", discover_spy)
    monkeypatch.setattr(pr, "research_product_via_websearch", _fake_research_makes_ready)

    job_id = _make_job("money_post")
    db = SessionLocal()
    try:
        # Pre-add 3 product URLs (as the user would).
        for i in range(3):
            product = Product(name=f"User Product {i}", brand=f"UB{i}", category="dehumidifier", extraction_status="pending")
            db.add(product)
            db.commit()
            db.refresh(product)
            db.add(ArticleJobProduct(article_job_id=job_id, product_id=product.id, source_url=f"https://u/{i}", source_type="retailer", extraction_status="pending"))
            db.commit()

        job = db.get(ArticleJob, job_id)
        result = wf.run_product_research(db, job)
        assert wf._draft_ready_count(job) == 3
        # 3 user URLs all became ready -> discovery should NOT have been needed.
        assert discover_called["n"] == 0
        assert "Discovered" not in result["message"]
    finally:
        db.close()


def test_auto_research_products_route(monkeypatch):
    from app.api.routes import article_jobs as routes

    monkeypatch.setattr(
        routes.workflow_service,
        "run_product_research",
        lambda db, job: {"message": "Product research complete: 3 draft-ready cards from 3 products."},
    )
    client = TestClient(app)
    job_id = _make_job("money_post")
    resp = client.post(f"/api/article-jobs/{job_id}/auto-research-products")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["action"] == "auto-research-products"
    assert body["status"] == "complete"
    assert "draft-ready" in body["message"]


def test_workflow_state_product_step_not_required_for_normal_post():
    job_id = _make_job("informational_blog")
    db = SessionLocal()
    try:
        job = db.get(ArticleJob, job_id)
        state = wf.get_workflow_state(db, job)
        steps = {s["step_key"]: s for s in state["steps"]}
        assert steps["product_research"]["status"] == "not_required"
    finally:
        db.close()
