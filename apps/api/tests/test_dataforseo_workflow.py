from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.db.session import SessionLocal
from app.models.entities import AppLog, CostLog, KeywordResearch, SerpResult
from app.services.dataforseo import DataForSEOClient, DataForSEOError
from fastapi.testclient import TestClient


class DummySerpClient:
    def fetch_google_serp(self, keyword: str, *, location_code: int = 2036, language_code: str = "en"):
        return type(
            "Result",
            (),
            {
                "endpoint": "serp/google/organic/live/advanced",
                "cost": 0.002,
                "result": [
                    {
                        "keyword": keyword,
                        "items": [
                            {
                                "type": "organic",
                                "rank_absolute": 1,
                                "title": "Best Dehumidifier",
                                "url": "https://example.com/best",
                                "domain": "example.com",
                                "description": "Snippet",
                            },
                            {
                                "type": "people_also_ask",
                                "rank_absolute": 2,
                                "items": [{"title": "Do dehumidifiers help mould?"}],
                            },
                        ],
                    }
                ],
            },
        )()


class DummyKeywordClient:
    def fetch_keyword_ideas(self, keyword: str, *, location_code: int = 2036, language_code: str = "en"):
        return type(
            "Result",
            (),
            {
                "endpoint": "dataforseo_labs/google/keyword_suggestions/live",
                "cost": 0.01,
                "result": [
                    {
                        "items": [
                            {
                                "keyword": f"{keyword} reviews",
                                "keyword_info": {
                                    "search_volume": 90,
                                    "cpc": 1.23,
                                    "competition_level": "LOW",
                                },
                                "keyword_properties": {
                                    "keyword_difficulty": 15,
                                },
                            }
                        ]
                    }
                ],
            },
        )()


@pytest.fixture()
def client():
    return TestClient(app)


def test_dataforseo_missing_credentials(monkeypatch):
    client = DataForSEOClient()
    monkeypatch.setattr(client.settings, "dataforseo_login", None)
    monkeypatch.setattr(client.settings, "dataforseo_password", None)
    with pytest.raises(DataForSEOError):
        client._credentials()


def test_run_serp_research_stores_results_and_logs(client, monkeypatch):
    article = client.post(
        "/api/article-jobs",
        json={
            "title": "SERP Test",
            "primary_keyword": "best dehumidifier australia",
            "post_type": "money_post",
        },
    ).json()
    monkeypatch.setattr("app.services.workflow.DataForSEOClient", lambda: DummySerpClient())

    response = client.post(f"/api/article-jobs/{article['id']}/run-serp-research")
    assert response.status_code == 200

    db = SessionLocal()
    try:
        assert db.query(SerpResult).filter(SerpResult.article_job_id == article["id"]).count() >= 1
        assert db.query(CostLog).filter(CostLog.related_entity_id == article["id"], CostLog.action == "serp_research").count() == 1
        event_types = [row.event_type for row in db.query(AppLog).filter(AppLog.article_job_id == article["id"]).all()]
        assert "workflow.serp_research.started" in event_types
        assert "workflow.serp_research.completed" in event_types
    finally:
        db.close()


def test_run_keyword_research_stores_results_and_logs(client, monkeypatch):
    article = client.post(
        "/api/article-jobs",
        json={
            "title": "Keyword Test",
            "primary_keyword": "dehumidifier for laundry",
            "post_type": "money_post",
        },
    ).json()
    monkeypatch.setattr("app.services.workflow.DataForSEOClient", lambda: DummyKeywordClient())

    response = client.post(f"/api/article-jobs/{article['id']}/run-keyword-research")
    assert response.status_code == 200

    db = SessionLocal()
    try:
        row = db.query(KeywordResearch).filter(KeywordResearch.article_job_id == article["id"]).first()
        assert row is not None
        assert row.search_volume == 90
        assert row.cpc == 1.23
        assert row.competition == "LOW"
        event_types = [log.event_type for log in db.query(AppLog).filter(AppLog.article_job_id == article["id"]).all()]
        assert "workflow.keyword_research.started" in event_types
        assert "workflow.keyword_research.completed" in event_types
    finally:
        db.close()


def test_run_serp_research_failure_logs_safely(client, monkeypatch):
    article = client.post(
        "/api/article-jobs",
        json={
            "title": "Failure Test",
            "primary_keyword": "laundry damp issues",
            "post_type": "informational_blog",
        },
    ).json()

    class FailingClient:
        def fetch_google_serp(self, keyword: str, *, location_code: int = 2036, language_code: str = "en"):
            raise DataForSEOError("DataForSEO request timed out.")

    monkeypatch.setattr("app.services.workflow.DataForSEOClient", lambda: FailingClient())

    response = client.post(f"/api/article-jobs/{article['id']}/run-serp-research")
    assert response.status_code == 502
    assert "timed out" in response.json()["detail"]

    db = SessionLocal()
    try:
        event_types = [log.event_type for log in db.query(AppLog).filter(AppLog.article_job_id == article["id"]).all()]
        assert "workflow.serp_research.failed" in event_types
    finally:
        db.close()
