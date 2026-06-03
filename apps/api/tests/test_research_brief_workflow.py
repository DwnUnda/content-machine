from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import ArticleBrief, ArticleDraft, ArticleJob, CompetitorAnalysisReport, CompetitorPage, KeywordResearch, QaReport, SerpResult, WorkflowRun
from app.services.workflow import get_workflow_state

def _seed_research(article_id: int) -> None:
    db = SessionLocal()
    try:
        db.add(
            SerpResult(
                article_job_id=article_id,
                keyword="best dehumidifier for mould australia",
                position=1,
                title="Best Dehumidifier for Mould in Australia",
                url="https://example.com.au/best",
                domain="example.com.au",
                result_type="organic",
            )
        )
        db.add(
            KeywordResearch(
                article_job_id=article_id,
                keyword="best dehumidifier australia",
                search_volume=1900,
                cpc=2.4,
                competition="medium",
                source="DataForSEO",
            )
        )
        db.add(
            CompetitorPage(
                article_job_id=article_id,
                title="Best Dehumidifier for Mould in Australia",
                url="https://example.com.au/best",
                domain="example.com.au",
                h2_list=["How we chose", "Running costs", "Who should avoid it"],
                h3_list=["Is it rental friendly?"],
                faq_headings=["Is it rental friendly?"],
                detected_product_names=["AusClimate NWT Medium 20L"],
                australian_relevance_score=72,
                extraction_status="success",
                page_type="affiliate/review site",
                visible_text_extract="Australian mould guide with running cost notes for rentals and laundry spaces.",
            )
        )
        db.add(
            CompetitorAnalysisReport(
                article_job_id=article_id,
                dominant_intent="commercial investigation",
                dominant_page_types_json={"affiliate/review site": 3, "retailer": 2},
                common_headings_json=["How we chose", "Running costs"],
                common_questions_json=["Is it rental friendly?"],
                repeated_products_json=["AusClimate NWT Medium 20L"],
                competitor_gaps_json=["Few competitors explain running costs clearly."],
                australian_context_gaps_json=["Many ranking pages use weak Australian context."],
                recommended_angle="Build a practical Australian buyer guide with downside-first product notes.",
                original_value_recommendations_json=["Add rental advice", "Summarise buyer complaints"],
                suggested_support_articles_json=["Dehumidifier running costs explained"],
                difficulty_estimate="medium",
                raw_report_json={"seeded": True},
            )
        )
        db.commit()
    finally:
        db.close()


def test_generate_research_brief_and_save():
    client = TestClient(app)
    article = client.post(
        "/api/article-jobs",
        json={"title": "Brief Test", "primary_keyword": "best dehumidifier for mould australia", "post_type": "money_post"},
    ).json()
    _seed_research(article["id"])

    response = client.post(f"/api/article-jobs/{article['id']}/generate-research-brief")
    assert response.status_code == 200

    briefs_response = client.get(f"/api/article-jobs/{article['id']}/briefs")
    assert briefs_response.status_code == 200
    brief = briefs_response.json()["items"][0]
    assert "research brief" in brief["brief_markdown"].lower()
    assert brief["outline_json"]["primary_keyword"] == "best dehumidifier for mould australia"
    assert brief["outline_json"]["recommended_article_angle"]

    save_response = client.put(
        f"/api/article-jobs/briefs/{brief['id']}",
        json={"brief_markdown": "# Edited brief"},
    )
    assert save_response.status_code == 200
    assert save_response.json()["brief_markdown"] == "# Edited brief"


def test_run_full_workflow_reuses_existing_research(monkeypatch):
    client = TestClient(app)
    article = client.post(
        "/api/article-jobs",
        json={"title": "Workflow Test", "primary_keyword": "best dehumidifier for mould australia", "post_type": "informational_blog"},
    ).json()
    _seed_research(article["id"])

    def fake_serp_research(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("SERP research should have been skipped")

    def fake_keyword_research(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("Keyword research should have been skipped")

    monkeypatch.setattr("app.services.workflow.run_serp_research", fake_serp_research)
    monkeypatch.setattr("app.services.workflow.run_keyword_research", fake_keyword_research)
    monkeypatch.setattr(
        "app.services.workflow.classify_serp_intent",
        lambda db, job: {"action": "classify serp intent", "article_job_id": job.id, "status": job.status, "message": "Classified."},  # noqa: ARG005
    )
    monkeypatch.setattr(
        "app.services.workflow.generate_draft",
        lambda db, job: {  # noqa: ARG005
            "action": "generate draft",
            "article_job_id": job.id,
            "status": job.status,
            "message": "Draft generated and saved.",
            "next_step": "Run human edit",
        },
    )
    monkeypatch.setattr(
        "app.services.workflow.run_australian_human_rewrite",
        lambda db, job: {  # noqa: ARG005
            "action": "run human edit",
            "article_job_id": job.id,
            "status": job.status,
            "message": "Australian human edit saved.",
            "next_step": "Run QA",
        },
    )
    monkeypatch.setattr(
        "app.services.workflow.run_qa",
        lambda db, job, stage="initial": {  # noqa: ARG005
            "action": "run QA",
            "article_job_id": job.id,
            "status": "Ready for review",
            "message": "QA passed and the final draft is ready for review.",
            "next_step": None,
        },
    )

    response = client.post(
        f"/api/article-jobs/{article['id']}/run-full-workflow",
        json={"research_mode": "reuse_existing"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "complete"
    statuses = {step["step_key"]: step["status"] for step in payload["steps"]}
    assert statuses["serp_research"] == "skipped"
    assert statuses["keyword_research"] == "skipped"
    assert statuses["competitor_extraction"] == "skipped"
    assert statuses["serp_analysis"] == "skipped"
    assert statuses["research_brief"] == "complete"
    assert statuses["draft_generation"] == "complete"
    assert statuses["human_edit"] == "complete"
    assert statuses["qa"] == "complete"

    db = SessionLocal()
    try:
        assert db.query(WorkflowRun).filter(WorkflowRun.article_job_id == article["id"]).count() == 1
        assert db.query(ArticleBrief).filter(ArticleBrief.article_job_id == article["id"]).count() >= 1
    finally:
        db.close()


def test_workflow_state_recommends_fix_pass_without_new_paid_calls(monkeypatch):
    client = TestClient(app)
    article = client.post(
        "/api/article-jobs",
        json={"title": "Resume Test", "primary_keyword": "best dehumidifier for mould australia", "post_type": "informational_blog"},
    ).json()
    _seed_research(article["id"])

    monkeypatch.setattr(
        "app.services.workflow._latest_completed_log_exists",
        lambda db, article_job_id, event_type: event_type == "workflow.keyword_research.completed",  # noqa: ARG005
    )

    db = SessionLocal()
    try:
        brief = ArticleBrief(
            article_job_id=article["id"],
            version=1,
            brief_markdown="# Brief",
            outline_json={"primary_keyword": article["primary_keyword"]},
        )
        db.add(brief)
        db.commit()

        draft = ArticleDraft(
            article_job_id=article["id"],
            version=1,
            stage="human_edit",
            draft_markdown="# Draft\n\nBody text",
            prompt_name="australian_human_edit_prompt.md",
        )
        db.add(draft)
        db.commit()

        qa = QaReport(
            article_job_id=article["id"],
            status="needs_revision",
            score=74,
            passed_gate=False,
            findings_json={"stage": "initial", "fix_instructions": ["Tighten unsupported claims."]},
            summary="QA failed.",
            prompt_name="qa_prompt.md",
        )
        db.add(qa)
        db.commit()

        state = get_workflow_state(db, db.get(ArticleJob, article["id"]))
        statuses = {step["step_key"]: step["status"] for step in state["steps"]}
        assert state["recommended_research_mode"] == "resume_current"
        assert state["next_recommended_action"] == "Run fix pass"
        assert state["estimated_paid_calls"] == 0
        assert statuses["serp_research"] == "complete"
        assert statuses["keyword_research"] == "complete"
        assert statuses["fix_pass"] == "missing"
        assert statuses["qa"] == "failed"
    finally:
        db.close()
