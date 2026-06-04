from pathlib import Path
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import ArticleBrief, ArticleDraft, ArticleJob, CompetitorAnalysisReport, CompetitorPage, KeywordResearch, QaReport, SerpResult, WorkflowRun
from app.services.research_brief import build_research_brief_payload
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


def test_research_brief_keeps_direct_question_informational_posts_focused():
    client = TestClient(app)
    article = client.post(
        "/api/article-jobs",
        json={
            "title": "Will A Dehumidifier Remove Existing Mould?",
            "primary_keyword": "Will A Dehumidifier Remove Existing Mould?",
            "post_type": "informational_blog",
        },
    ).json()

    db = SessionLocal()
    try:
        db.add(
            CompetitorAnalysisReport(
                article_job_id=article["id"],
                dominant_intent="commercial investigation",
                competitor_gaps_json=["Few competitors discuss running costs clearly."],
                australian_context_gaps_json=["Rental suitability is under-covered."],
                recommended_angle="Build an Australian buyer-first guide that compares mould control, running cost, and rental suitability.",
                original_value_recommendations_json=[
                    "Add stronger Australian climate, pricing, and rental context.",
                    "Add a running cost explainer for Australian households.",
                    "Add rental-friendly guidance and limitations.",
                ],
                common_questions_json=[
                    "Will running a dehumidifier kill mould?",
                    "Can I run a dehumidifier while there is mould?",
                    "What humidity level stops mould?",
                    "Is it worth it after rain?",
                    "When should I call a professional?",
                    "How do I prevent mould coming back?",
                    "How do I choose a dehumidifier?",
                ],
                raw_report_json={"seeded": True},
            )
        )
        db.commit()

        payload = build_research_brief_payload(db, db.get(ArticleJob, article["id"]))
        assert payload["search_intent"] == "informational support"
        assert "Do not turn this into a buyer guide" in payload["recommended_article_angle"]
        assert "running cost explainer" not in " ".join(payload["original_value_points"]).lower()
        assert len(payload["faq_questions"]) == 5
        assert payload["required_sections"] == [
            "short answer",
            "when it helps",
            "when it will not help",
            "what to do next",
            "when to get professional help if relevant",
            "FAQ",
            "final answer",
        ]
    finally:
        db.close()


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
    monkeypatch.setattr("app.services.workflow.get_settings", lambda: SimpleNamespace(openai_api_key=None))

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


def test_run_full_workflow_rechecks_reused_fix_pass(monkeypatch):
    client = TestClient(app)
    article = client.post(
        "/api/article-jobs",
        json={"title": "Humidity Mould", "primary_keyword": "what humidity causes mould", "post_type": "informational_blog"},
    ).json()

    old_time = datetime.utcnow() - timedelta(minutes=10)
    new_time = datetime.utcnow() - timedelta(minutes=1)
    with SessionLocal() as db:
        db.add(
            ArticleDraft(
                article_job_id=article["id"],
                version=1,
                stage="human_edit",
                draft_markdown="# Draft\n\nBody text",
                prompt_name="australian_human_edit_prompt.md",
                created_at=old_time,
                updated_at=old_time,
            )
        )
        db.add(
            QaReport(
                article_job_id=article["id"],
                status="needs_revision",
                score=80,
                passed_gate=False,
                findings_json={"stage": "initial", "failed_checks": ["Needs sharper answer."]},
                summary="QA failed.",
                prompt_name="qa_prompt.md",
                created_at=old_time,
                updated_at=old_time,
            )
        )
        db.add(
            ArticleDraft(
                article_job_id=article["id"],
                version=2,
                stage="fix_pass",
                draft_markdown="# Fixed draft\n\nSharper answer.",
                prompt_name="fix_pass_prompt.md",
                created_at=new_time,
                updated_at=new_time,
            )
        )
        db.commit()

    generic_result = lambda db, job: {  # noqa: E731, ARG005
        "action": "noop",
        "article_job_id": job.id,
        "status": job.status,
        "message": "Done.",
    }
    for name in (
        "run_serp_research",
        "run_keyword_research",
        "extract_competitors",
        "analyse_serp",
        "classify_serp_intent",
        "generate_brief",
        "run_product_research",
        "run_reddit_feedback_research",
        "generate_draft",
        "run_australian_human_rewrite",
    ):
        monkeypatch.setattr(f"app.services.workflow.{name}", generic_result)
    monkeypatch.setattr(
        "app.services.workflow.get_drafting_readiness",
        lambda db, job: {"can_generate_draft": True, "issues": []},  # noqa: ARG005
    )
    monkeypatch.setattr(
        "app.services.workflow.get_workflow_state",
        lambda db, job: {  # noqa: ARG005
            "steps": [
                {
                    "step_key": step_key,
                    "status": status,
                    "detail": "",
                    "paid_step": False,
                }
                for step_key, status in {
                    "serp_research": "complete",
                    "keyword_research": "complete",
                    "competitor_extraction": "complete",
                    "serp_analysis": "complete",
                    "serp_intent": "complete",
                    "research_brief": "complete",
                    "product_research": "not_required",
                    "reddit_feedback": "complete",
                    "draft_generation": "complete",
                    "human_edit": "complete",
                    "qa": "stale",
                    "fix_pass": "complete",
                    "qa_recheck": "missing",
                }.items()
            ]
        },
    )

    qa_stages: list[str] = []

    def fake_qa(db, job, stage="initial"):  # noqa: ANN001
        qa_stages.append(stage)
        if stage == "initial":
            job.status = "QA failed"
            message = "QA completed. The draft needs a fix pass before it can be marked ready for review."
        else:
            job.status = "Ready for review"
            message = "QA passed and the final draft is ready for review."
        db.add(job)
        db.commit()
        return {
            "action": "run QA",
            "article_job_id": job.id,
            "status": job.status,
            "message": message,
            "next_step": None,
        }

    monkeypatch.setattr("app.services.workflow.run_qa", fake_qa)
    monkeypatch.setattr(
        "app.services.workflow.run_ai_fix_pass",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Existing fix pass should be reused")),  # noqa: ARG005
    )

    response = client.post(
        f"/api/article-jobs/{article['id']}/run-full-workflow",
        json={"research_mode": "resume_current"},
    )
    assert response.status_code == 200
    payload = response.json()
    statuses = {step["step_key"]: step["status"] for step in payload["steps"]}
    assert statuses["fix_pass"] == "skipped"
    assert statuses["qa_recheck"] == "complete"
    assert qa_stages == ["initial", "recheck"]
