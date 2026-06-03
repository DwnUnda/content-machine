from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import (
    AppLog,
    ArticleBrief,
    ArticleDraft,
    ArticleJob,
    ArticleJobProduct,
    CompetitorAnalysisReport,
    CompetitorPage,
    InternalLink,
    KeywordResearch,
    Product,
    ProductSource,
    QaReport,
    SerpResult,
    Source,
    StandardPostBatch,
    StandardPostBatchItem,
    WordPressExport,
    WorkflowRun,
    WorkflowRunStep,
)


def test_delete_article_job_removes_local_article_records(monkeypatch, tmp_path):
    export_root = tmp_path / "Completed-Articles"
    monkeypatch.setattr("app.core.config.COMPLETED_ARTICLES_DIR", export_root)
    monkeypatch.setattr("app.services.local_exports.COMPLETED_ARTICLES_DIR", export_root)

    client = TestClient(app)
    created = client.post(
        "/api/article-jobs",
        json={
            "title": "Delete Me",
            "primary_keyword": "best test dehumidifier",
            "post_type": "money_post",
        },
    ).json()
    job_id = created["id"]
    export_path = Path(client.get(f"/api/article-jobs/{job_id}").json()["local_export_path"])

    with SessionLocal() as db:
        product = Product(name="Test Dehumidifier")
        db.add(product)
        db.flush()

        source = Source(
            article_job_id=job_id,
            title="Test source",
            url="https://example.com/source",
            source_type="retailer",
        )
        db.add(source)
        db.flush()

        workflow_run = WorkflowRun(
            article_job_id=job_id,
            workflow_mode="full",
            research_mode="local",
            status="running",
            current_step="draft",
        )
        batch = StandardPostBatch(name="Test batch")
        db.add_all(
            [
                ProductSource(product_id=product.id, source_id=source.id),
                SerpResult(article_job_id=job_id, keyword="test"),
                KeywordResearch(article_job_id=job_id, keyword="test"),
                CompetitorPage(article_job_id=job_id, title="Competitor", url="https://example.com/competitor"),
                CompetitorAnalysisReport(article_job_id=job_id),
                ArticleBrief(article_job_id=job_id, version=1),
                ArticleDraft(article_job_id=job_id, version=1),
                QaReport(article_job_id=job_id, status="passed"),
                WordPressExport(article_job_id=job_id, export_status="draft_created", wordpress_status="draft"),
                InternalLink(article_job_id=job_id, anchor_text="Anchor", target_url="https://example.com/internal"),
                ArticleJobProduct(
                    article_job_id=job_id,
                    product_id=product.id,
                    source_url="https://example.com/product",
                    source_type="retailer",
                ),
                workflow_run,
                batch,
            ]
        )
        db.flush()
        db.add(WorkflowRunStep(workflow_run_id=workflow_run.id, step_key="draft", step_label="Draft", status="running"))
        db.add(StandardPostBatchItem(batch_id=batch.id, keyword="test", position=1, article_job_id=job_id))
        product_id = product.id
        db.commit()

    response = client.delete(f"/api/article-jobs/{job_id}")

    assert response.status_code == 204
    assert not export_path.exists()

    with SessionLocal() as db:
        assert db.get(ArticleJob, job_id) is None
        for model in (
            AppLog,
            Source,
            ProductSource,
            SerpResult,
            KeywordResearch,
            CompetitorPage,
            CompetitorAnalysisReport,
            ArticleBrief,
            ArticleDraft,
            QaReport,
            WordPressExport,
            InternalLink,
            ArticleJobProduct,
            WorkflowRun,
            WorkflowRunStep,
        ):
            assert db.scalar(select(model.id).limit(1)) is None
        assert db.scalar(select(Product.id).where(Product.name == "Test Dehumidifier")) == product_id
        batch_item = db.scalar(select(StandardPostBatchItem))
        assert batch_item is not None
        assert batch_item.article_job_id is None
