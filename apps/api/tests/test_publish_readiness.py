from pathlib import Path
import sys
from datetime import datetime

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import ArticleDraft, ArticleJob, QaReport
from app.services.workflow import build_publish_readiness, export_to_wordpress_draft


def test_publish_readiness_blocks_without_final_draft(monkeypatch, tmp_path):
    export_root = tmp_path / "Completed-Articles"
    monkeypatch.setattr("app.core.config.COMPLETED_ARTICLES_DIR", export_root)
    monkeypatch.setattr("app.services.local_exports.COMPLETED_ARTICLES_DIR", export_root)

    client = TestClient(app)
    created = client.post(
        "/api/article-jobs",
        json={"title": "Readiness Test", "primary_keyword": "humidity", "post_type": "informational_blog"},
    ).json()

    with SessionLocal() as db:
        readiness = build_publish_readiness(db, db.get(ArticleJob, created["id"]))

    assert readiness["ready"] is False
    failed = {check["key"] for check in readiness["checks"] if not check["passed"]}
    assert "final_draft" in failed
    assert "qa_passed" in failed
    assert "html_generated" in failed


def test_publish_readiness_passes_for_final_informational_article(monkeypatch, tmp_path):
    export_root = tmp_path / "Completed-Articles"
    monkeypatch.setattr("app.core.config.COMPLETED_ARTICLES_DIR", export_root)
    monkeypatch.setattr("app.services.local_exports.COMPLETED_ARTICLES_DIR", export_root)

    client = TestClient(app)
    created = client.post(
        "/api/article-jobs",
        json={"title": "Readiness Pass", "primary_keyword": "humidity", "post_type": "informational_blog"},
    ).json()

    draft_body = (
        "# Readiness Pass\n\n"
        "Humidity control matters in Australian homes.\n\n"
        "## Practical steps\n\n"
        "Keep rooms ventilated and track indoor humidity.\n\n"
        "## Frequently asked questions\n\n"
        "### What humidity should I aim for?\n\n"
        "Aim for a practical range that limits condensation without over-drying the room.\n\n"
        "## Final thoughts\n\n"
        "Focus on the source of moisture first, then use appliances where they genuinely help."
    )
    with SessionLocal() as db:
        db.add(
            ArticleDraft(
                article_job_id=created["id"],
                version=1,
                stage="final",
                draft_markdown=draft_body,
                slug="readiness-pass",
            )
        )
        db.add(QaReport(article_job_id=created["id"], status="pass", score=91, passed_gate=True))
        db.commit()
        job = db.get(ArticleJob, created["id"])
        from app.services.local_exports import sync_article_export

        sync_article_export(db, job, reason="test_publish_readiness")
        readiness = build_publish_readiness(db, job)

    assert readiness["ready"] is True
    assert readiness["html_validation"]["passed"] is True


def test_wordpress_export_refuses_not_ready_article(monkeypatch, tmp_path):
    export_root = tmp_path / "Completed-Articles"
    monkeypatch.setattr("app.core.config.COMPLETED_ARTICLES_DIR", export_root)
    monkeypatch.setattr("app.services.local_exports.COMPLETED_ARTICLES_DIR", export_root)

    client = TestClient(app)
    created = client.post(
        "/api/article-jobs",
        json={"title": "Blocked Upload", "primary_keyword": "humidity", "post_type": "informational_blog"},
    ).json()

    with SessionLocal() as db:
        job = db.get(ArticleJob, created["id"])
        with pytest.raises(ValueError, match="not ready for WordPress"):
            export_to_wordpress_draft(db, job)


def test_local_export_uses_highest_id_for_same_timestamp_latest_qa(monkeypatch, tmp_path):
    export_root = tmp_path / "Completed-Articles"
    monkeypatch.setattr("app.core.config.COMPLETED_ARTICLES_DIR", export_root)
    monkeypatch.setattr("app.services.local_exports.COMPLETED_ARTICLES_DIR", export_root)

    client = TestClient(app)
    created = client.post(
        "/api/article-jobs",
        json={"title": "QA Latest", "primary_keyword": "humidity", "post_type": "informational_blog"},
    ).json()

    same_time = datetime.utcnow()
    with SessionLocal() as db:
        db.add(QaReport(article_job_id=created["id"], status="needs_revision", score=80, passed_gate=False, created_at=same_time))
        db.commit()
        db.add(QaReport(article_job_id=created["id"], status="pass", score=91, passed_gate=True, created_at=same_time))
        db.commit()
        job = db.get(ArticleJob, created["id"])
        from app.services.local_exports import sync_article_export

        root = sync_article_export(db, job, reason="test_latest_qa_order")

    import json

    latest = json.loads((root / "qa" / "latest.json").read_text(encoding="utf-8"))
    assert latest["status"] == "pass"
    assert latest["score"] == 91
