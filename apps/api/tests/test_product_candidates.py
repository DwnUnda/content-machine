from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import ArticleJobProduct, CompetitorAnalysisReport, CompetitorPage, CostLog, Product, ProductCandidate, SerpResult
from app.services.product_research import NOT_CONFIRMED

def _create_article(client: TestClient) -> dict:
    return client.post(
        "/api/article-jobs",
        json={"title": "Candidate Test", "primary_keyword": "best dehumidifier for mould australia", "post_type": "money_post"},
    ).json()


def _seed_candidate_sources(article_id: int) -> None:
    db = SessionLocal()
    try:
        db.add(
            CompetitorPage(
                article_job_id=article_id,
                title="Best Dehumidifier for Mould in Australia",
                url="https://example.com.au/best",
                domain="example.com.au",
                detected_product_names=["AusClimate NWT Medium 20L", "Ionmax ION632"],
                h2_list=["AusClimate NWT Medium 20L review", "Ionmax ION632 review"],
                extraction_status="success",
                page_type="affiliate/review site",
            )
        )
        db.add(
            CompetitorAnalysisReport(
                article_job_id=article_id,
                dominant_intent="commercial investigation",
                repeated_products_json=["AusClimate NWT Medium 20L", "Midea FreshDry MDDQ12"],
                recommended_angle="Practical buyer guide",
            )
        )
        db.add(
            SerpResult(
                article_job_id=article_id,
                keyword="best dehumidifier for mould australia",
                position=1,
                title="Best dehumidifier: AusClimate NWT Medium 20L vs Ionmax ION632",
                url="https://example.com.au/serp",
                domain="example.com.au",
                result_type="organic",
            )
        )
        db.commit()
    finally:
        db.close()


def test_extracting_candidates_from_mocked_competitor_data(monkeypatch):
    client = TestClient(app)
    article = _create_article(client)
    _seed_candidate_sources(article["id"])

    class FailingClient:
        def __init__(self, *args, **kwargs):  # noqa: ARG002, D401
            raise AssertionError("Paid discovery should not run when stored data already found enough candidates")

    monkeypatch.setattr("app.services.product_candidates.DataForSEOClient", FailingClient)

    response = client.post(f"/api/article-jobs/{article['id']}/find-product-candidates")
    assert response.status_code == 200
    assert "Found" in response.json()["message"]

    candidates = client.get(f"/api/article-jobs/{article['id']}/product-candidates").json()["items"]
    names = {item["product_name"] for item in candidates}
    assert "AusClimate NWT Medium 20L" in names
    assert "Ionmax ION632" in names


def test_candidate_approval_and_conversion_creates_product_card():
    client = TestClient(app)
    article = _create_article(client)
    _seed_candidate_sources(article["id"])

    client.post(f"/api/article-jobs/{article['id']}/find-product-candidates")
    candidate = client.get(f"/api/article-jobs/{article['id']}/product-candidates").json()["items"][0]

    approve_response = client.post(f"/api/article-jobs/{article['id']}/product-candidates/{candidate['id']}/approve")
    assert approve_response.status_code == 200

    convert_response = client.post(
        f"/api/article-jobs/{article['id']}/product-candidates/{candidate['id']}/convert",
        json={"auto_extract": False},
    )
    assert convert_response.status_code == 200
    payload = convert_response.json()
    assert payload["candidate"]["status"] == "converted"
    assert payload["product_link"]["product"]["best_for"] == NOT_CONFIRMED
    assert payload["product_link"]["draft_ready"] is False

    db = SessionLocal()
    try:
        assert db.query(ArticleJobProduct).filter(ArticleJobProduct.article_job_id == article["id"]).count() == 1
        assert db.query(Product).count() == 1
    finally:
        db.close()


def test_ignored_candidates_remain_unused():
    client = TestClient(app)
    article = _create_article(client)
    _seed_candidate_sources(article["id"])

    client.post(f"/api/article-jobs/{article['id']}/find-product-candidates")
    candidate = client.get(f"/api/article-jobs/{article['id']}/product-candidates").json()["items"][0]
    ignore_response = client.post(f"/api/article-jobs/{article['id']}/product-candidates/{candidate['id']}/ignore")
    assert ignore_response.status_code == 200

    client.post(f"/api/article-jobs/{article['id']}/find-product-candidates")
    refreshed = client.get(f"/api/article-jobs/{article['id']}/product-candidates").json()["items"]
    ignored = next(item for item in refreshed if item["id"] == candidate["id"])
    assert ignored["status"] == "ignored"

    db = SessionLocal()
    try:
        assert db.query(ArticleJobProduct).count() == 0
    finally:
        db.close()


def test_paid_discovery_search_not_run_automatically():
    client = TestClient(app)
    article = _create_article(client)
    _seed_candidate_sources(article["id"])

    db = SessionLocal()
    try:
        assert db.query(ProductCandidate).count() == 0
    finally:
        db.close()


def test_paid_discovery_search_can_fill_candidates_when_needed(monkeypatch):
    client = TestClient(app)
    article = _create_article(client)

    class DummyClient:
        def fetch_google_serp(self, keyword: str, *, location_code: int = 2036, language_code: str = "en", depth: int = 10):  # noqa: ARG002
            return type(
                "Result",
                (),
                {
                    "endpoint": "serp/google/organic/live/advanced",
                    "cost": 0.004,
                    "response_json": {"ok": True},
                    "result": [
                        {
                            "items": [
                                {
                                    "type": "organic",
                                    "title": "The Good Guys: Midea FreshDry MDDQ12 dehumidifier",
                                    "description": "Midea FreshDry MDDQ12 product page",
                                    "url": "https://www.thegoodguys.com.au/midea-freshdry-mddq12",
                                    "domain": "thegoodguys.com.au",
                                }
                            ]
                        }
                    ],
                },
            )()

    monkeypatch.setattr("app.services.product_candidates.DataForSEOClient", lambda: DummyClient())

    response = client.post(f"/api/article-jobs/{article['id']}/find-product-candidates")
    assert response.status_code == 200

    candidates = client.get(f"/api/article-jobs/{article['id']}/product-candidates").json()["items"]
    assert any("Midea FreshDry MDDQ12" in item["product_name"] for item in candidates)

    db = SessionLocal()
    try:
        assert db.query(CostLog).filter(CostLog.related_entity_id == article["id"], CostLog.action == "product_candidate_discovery").count() >= 1
    finally:
        db.close()
