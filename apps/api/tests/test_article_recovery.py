from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AppLog, ArticleBrief, ArticleDraft, ArticleJob, CompetitorAnalysisReport, CompetitorPage, KeywordResearch, QaReport, SerpResult, WorkflowRun
from app.services.workflow import get_workflow_state


def test_restore_article_from_completed_articles_bundle():
    bundle_root = (
        Path(__file__).resolve().parents[3]
        / "Completed-Articles"
        / "articles"
        / "article-3-what-humidity-level-causes-mould-in-australian-homes"
    )
    client = TestClient(app)

    response = client.post(
        "/api/article-jobs/recover-from-export",
        json={"bundle_path": str(bundle_root)},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == 3
    assert payload["title"] == "What humidity level causes mould in Australian homes?"

    articles = client.get("/api/article-jobs").json()
    assert any(article["id"] == 3 for article in articles)

    db = SessionLocal()
    try:
        job = db.get(ArticleJob, 3)
        assert job is not None
        assert db.query(SerpResult).filter(SerpResult.article_job_id == 3).count() > 0
        assert db.query(KeywordResearch).filter(KeywordResearch.article_job_id == 3).count() >= 0
        assert db.query(CompetitorPage).filter(CompetitorPage.article_job_id == 3).count() > 0
        assert db.query(CompetitorAnalysisReport).filter(CompetitorAnalysisReport.article_job_id == 3).count() > 0
        assert db.query(ArticleBrief).filter(ArticleBrief.article_job_id == 3).count() > 0
        assert db.query(ArticleDraft).filter(ArticleDraft.article_job_id == 3).count() > 0
        assert db.query(QaReport).filter(QaReport.article_job_id == 3).count() > 0
        assert db.query(WorkflowRun).filter(WorkflowRun.article_job_id == 3).count() > 0
        assert db.query(AppLog).filter(AppLog.article_job_id == 3, AppLog.event_type == "article_job.recovered").count() == 1

        state = get_workflow_state(db, job)
        assert state["recommended_research_mode"] == "resume_current"
        assert state["next_recommended_action"] in {"Run QA", "Run fix pass"}
        assert state["estimated_paid_calls"] == 0
    finally:
        db.close()
