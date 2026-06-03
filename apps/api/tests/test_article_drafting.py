from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import ArticleBrief, ArticleDraft, ArticleJob, ArticleJobProduct, CompetitorAnalysisReport, CompetitorPage, ContentCluster, KeywordResearch, Product, QaReport, SerpResult
from app.services import article_drafting as ad
from app.services.anthropic_client import AnthropicClient, AnthropicError
from app.services.article_drafting import generate_draft, run_fix_pass, run_human_edit, run_qa
from app.services.openai_client import OpenAIClient, OpenAIError
from app.services.workflow import get_drafting_readiness, set_manual_review_override

def _create_job(client: TestClient, post_type: str = "informational_blog") -> dict:
    return client.post(
        "/api/article-jobs",
        json={"title": "Product Draft Test", "primary_keyword": "best dehumidifier", "post_type": post_type},
    ).json()


def _seed_brief(db, job_id: int) -> None:
    brief = ArticleBrief(
        article_job_id=job_id,
        version=1,
        brief_markdown="# Research Brief\n\n- Test",
        serp_intent_json={"primary_intent": "commercial investigation", "content_type": "buying guide"},
        outline_json={
            "primary_keyword": "best dehumidifier",
            "search_intent": "buying",
            "reader_profile": "Australian homeowners",
            "recommended_article_angle": "Practical guide",
            "secondary_keywords": ["dehumidifier australia"],
            "competitor_gaps": ["Australian context"],
            "australian_context_gaps": ["Running costs"],
            "required_sections": ["quick answer"],
            "original_value_points": ["Value"],
            "internal_link_suggestions": ["/guides/dehumidifier"],
            "faq_questions": ["What size dehumidifier do I need?"],
            "suggested_title_options": ["Best dehumidifier"],
            "suggested_slug": "best-dehumidifier",
            "meta_description_draft": "Meta",
        },
    )
    db.add(brief)
    db.commit()


def _long_markdown(word: str, count: int) -> str:
    return "# Draft\n\n" + " ".join([word] * count)


def _incomplete_markdown(word: str, count: int) -> str:
    body = "# Draft\n\n" + " ".join([word] * count)
    body += "\n\n## FAQ\n\n### What should I do next?\n\nThis answer is incomplete."
    return body


def _complete_markdown(word: str, count: int) -> str:
    return (
        "# Draft\n\n"
        + " ".join([word] * count)
        + "\n\n## FAQ\n\n### What should I do next?\n\nDo the practical next step.\n\n## Final Recommendation\n\nUse the approach that best fits the home."
    )


def test_ai_clients_fail_safely_without_credentials(monkeypatch):
    monkeypatch.setattr("app.services.openai_client.get_settings", lambda: SimpleNamespace(openai_api_key=None, openai_model=None))
    monkeypatch.setattr("app.services.anthropic_client.get_settings", lambda: SimpleNamespace(anthropic_api_key=None, anthropic_model=None))

    with pytest.raises(OpenAIError):
        OpenAIClient().generate_text(instructions="x", input_text="y")

    with pytest.raises(AnthropicError):
        AnthropicClient().generate_text(system_prompt="x", user_prompt="y")


def test_not_confirmed_product_specs_are_not_invented(monkeypatch):
    client = TestClient(app)
    job = _create_job(client)
    db = SessionLocal()
    try:
        _seed_brief(db, job["id"])
        product = Product(
            name="Example Product",
            brand="Example",
            category="dehumidifier",
            product_url="https://example.com.au/product",
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        link = ArticleJobProduct(
            article_job_id=job["id"],
            product_id=product.id,
            source_url="https://example.com.au/product",
            source_type="manufacturer",
            extraction_status="success",
        )
        db.add(link)
        db.commit()

        captured = {}

        def fake_generate_text(self, *, system_prompt, user_prompt, model=None, max_tokens=4000, cache=True):  # noqa: ARG001
            captured["user_prompt"] = user_prompt
            return SimpleNamespace(content_text=_complete_markdown("Best", 1250), model=model or "test-model")

        monkeypatch.setattr(AnthropicClient, "generate_text", fake_generate_text)

        result = generate_draft(db, db.get(ArticleJob, job["id"]))
        assert result["message"] == "Draft generated and saved."
        assert "Not confirmed" in captured["user_prompt"]

        saved = db.query(ArticleDraft).filter(ArticleDraft.article_job_id == job["id"]).order_by(ArticleDraft.version.desc()).first()
        assert saved is not None
        assert saved.stage == "first_draft"
    finally:
        db.close()


def test_generate_draft_repairs_truncated_tail(monkeypatch):
    client = TestClient(app)
    job = _create_job(client)
    db = SessionLocal()
    try:
        _seed_brief(db, job["id"])
        db.add(
            CompetitorAnalysisReport(
                article_job_id=job["id"],
                dominant_intent="informational",
                recommended_angle="Practical guide",
            )
        )
        db.commit()

        calls = []

        def fake_generate_text(self, *, system_prompt, user_prompt, model=None, max_tokens=4000, cache=True):  # noqa: ARG001
            calls.append(max_tokens)
            draft_body = "# Draft\n\n" + " ".join(["draft"] * 1250)
            draft_body += "\n\n## FAQ\n\n### What should I do next?\n\nThis answer is incomplete."
            return SimpleNamespace(content_text=draft_body, model=model or "test-model")

        def fake_generate_json(self, *, system_prompt, user_prompt, model=None, max_tokens=4000):  # noqa: ARG001
            calls.append(max_tokens)
            return {
                "draft_markdown": (
                    "## FAQ\n\n"
                    "### Is this helpful?\n\n"
                    "Yes.\n\n"
                    "## Final Recommendation\n\n"
                    "Use this approach if you need a practical Australian guide."
                ),
                "notes": ["repair"],
                "title_options": ["Repair"],
            }

        monkeypatch.setattr(AnthropicClient, "generate_text", fake_generate_text)
        monkeypatch.setattr(AnthropicClient, "generate_json", fake_generate_json)

        result = generate_draft(db, db.get(ArticleJob, job["id"]))
        assert result["status"] == "Draft complete"
        # Informational posts use the standard cap (12000); the tail repair now
        # gets a higher ceiling so a complete ending can still fit after richer
        # content-module and renderer requirements.
        assert calls == [12000, 10000]

        saved = db.query(ArticleDraft).filter(ArticleDraft.article_job_id == job["id"]).order_by(ArticleDraft.version.desc()).first()
        assert saved is not None
        assert "## FAQ" in saved.draft_markdown
        assert "## Final Recommendation" in saved.draft_markdown
        assert not saved.draft_markdown.strip().endswith("incomplete.")
    finally:
        db.close()


def test_draft_completion_accepts_frequently_asked_questions_heading():
    draft = (
        "# Draft\n\n"
        + " ".join(["draft"] * 1250)
        + "\n\n## Frequently asked questions\n\n"
        "### What should I do next?\n\n"
        "Do the practical next step.\n\n"
        "## Final recommendation\n\n"
        "Use the approach that best fits the home."
    )
    job = ArticleJob(post_type="informational_blog")

    issues = ad._draft_completion_issues(draft, job)

    assert issues == []


def test_draft_payload_reads_content_modules():
    payload = ad._draft_payload_from_response({
        "draft_markdown": "<article><h2>Quick comparison</h2><p>Body</p></article>",
        "content_modules": [
            {"module_type": "comparison", "heading": "Quick comparison"},
            {"module_type": "final_verdict", "heading": "Final recommendation"},
        ],
    })

    assert payload.content_modules == [
        {"module_type": "comparison", "heading": "Quick comparison"},
        {"module_type": "final_verdict", "heading": "Final recommendation"},
    ]


def test_infer_content_modules_for_best_x_for_y():
    draft = (
        "<article>"
        '<div class="top-picks-grid"><div class="product-card featured"><h3>Pick</h3></div></div>'
        "<h2>Which one suits your situation?</h2><p>Body</p>"
        "<h2>Quick comparison</h2><p>Body</p>"
        "<h2>How we chose these products</h2><p>Body</p>"
        "<h2>How to choose for mould</h2><p>Body</p>"
        "<h2>Common mistakes when buying for mould</h2><p>Body</p>"
        "<h2>Final recommendation</h2><p>Body</p>"
        "</article>"
    )

    modules = ad._infer_content_modules(draft, "best_x_for_y")

    assert {"module_type": "top_picks", "heading": "Top picks"} in modules
    assert {"module_type": "jump_links", "heading": "Jump links"} in modules
    assert {"module_type": "decision_grid", "heading": "Which one suits your situation?"} in modules
    assert {"module_type": "comparison", "heading": "Quick comparison"} in modules
    assert {"module_type": "methodology", "heading": "How we chose these products"} in modules
    assert {"module_type": "buyer_guide", "heading": "How to choose for"} in modules
    assert {"module_type": "mistakes", "heading": "Common mistakes when buying for"} in modules
    assert {"module_type": "final_verdict", "heading": "Final recommendation"} in modules


def test_draft_token_cap_is_higher_for_commercial_posts():
    assert ad._draft_max_output_tokens(ArticleJob(post_type="informational_blog")) == 12000
    assert ad._draft_max_output_tokens(ArticleJob(post_type="single_product_review")) == 20000
    assert ad._draft_max_output_tokens(ArticleJob(post_type="product_comparison")) == 22000
    assert ad._draft_max_output_tokens(ArticleJob(post_type="money_post")) == 24000
    assert ad._draft_max_output_tokens(ArticleJob(post_type="best_x_for_y")) == 24000


def test_serialise_product_includes_best_effort_image_url():
    product = Product(
        name="Example Purifier",
        product_url="https://example.com/product",
        raw_extracted_json={
            "media": {
                "primary_image_url": "https://cdn.example.com/images/purifier.webp",
            }
        },
    )

    serialised = ad._serialise_product(product)

    assert serialised["product_url"] == "https://example.com/product"
    assert serialised["product_image_url"] == "https://cdn.example.com/images/purifier.webp"


def test_qa_below_85_triggers_fix_pass_and_override(monkeypatch):
    client = TestClient(app)
    job = _create_job(client)
    db = SessionLocal()
    try:
        _seed_brief(db, job["id"])

        anthropic_payloads = [
            _complete_markdown("initial", 1250),
            _complete_markdown("edited", 1250),
            _complete_markdown("revised", 1250),
        ]
        openai_payloads = [
            {
                "score": 80,
                "passed": False,
                "failed_checks": ["AI slop phrases"],
                "warnings": ["Needs a fix pass."],
                "fix_instructions": ["Trim repetitive phrasing", "Add clearer drawbacks"],
                "manual_override_risk": "medium",
                "summary": "Below threshold.",
            },
            {
                "seo_title": "Best Dehumidifier",
                "meta_description": "Practical Australian guide.",
                "slug": "best-dehumidifier",
                "excerpt": "Practical guide excerpt.",
                "social_summary": "Social summary.",
            },
            {
                "score": 90,
                "passed": True,
                "failed_checks": [],
                "warnings": [],
                "fix_instructions": [],
                "manual_override_risk": "low",
                "summary": "Passed after fix.",
            },
            {
                "seo_title": "Best Dehumidifier",
                "meta_description": "Practical Australian guide.",
                "slug": "best-dehumidifier",
                "excerpt": "Practical guide excerpt.",
                "social_summary": "Social summary.",
            },
        ]

        def fake_anthropic_generate_text(self, *, system_prompt, user_prompt, model=None, max_tokens=4000, cache=True):  # noqa: ARG001
            return SimpleNamespace(content_text=anthropic_payloads.pop(0), model=model or "test-model")

        def fake_openai_generate_json(self, *, instructions, input_text, model=None, max_output_tokens=4000, cache_key=None):  # noqa: ARG001
            return openai_payloads.pop(0)

        monkeypatch.setattr(AnthropicClient, "generate_text", fake_anthropic_generate_text)
        monkeypatch.setattr(OpenAIClient, "generate_json", fake_openai_generate_json)

        generate_draft(db, db.get(ArticleJob, job["id"]))
        run_human_edit(db, db.get(ArticleJob, job["id"]))
        qa_result = run_qa(db, db.get(ArticleJob, job["id"]))
        assert qa_result["status"] == "QA failed"

        job_row = db.get(ArticleJob, job["id"])
        assert job_row.status == "QA failed"

        fix_result = run_fix_pass(db, job_row)
        assert fix_result["message"] == "Fix pass saved. Run QA again to confirm the score."

        recheck_result = run_qa(db, db.get(ArticleJob, job["id"]), stage="recheck")
        assert recheck_result["status"] == "Ready for review"

        job_row = db.get(ArticleJob, job["id"])
        assert job_row.status == "Ready for review"
        assert job_row.current_qa_score == 90

        saved_drafts = db.query(ArticleDraft).filter(ArticleDraft.article_job_id == job["id"]).all()
        stages = [draft.stage for draft in saved_drafts]
        assert "first_draft" in stages
        assert "human_edit" in stages
        assert "fix_pass" in stages
        assert "final" in stages
    finally:
        db.close()


def test_manual_override_allows_ready_for_review_below_threshold(monkeypatch):
    client = TestClient(app)
    job = _create_job(client)
    db = SessionLocal()
    try:
        _seed_brief(db, job["id"])

        monkeypatch.setattr(
            AnthropicClient,
            "generate_text",
            lambda self, **kwargs: SimpleNamespace(content_text=_complete_markdown("Body", 1250), model="test-model"),  # noqa: ARG005
        )
        monkeypatch.setattr(
            OpenAIClient,
            "generate_json",
            lambda self, **kwargs: {"score": 70, "passed": False, "failed_checks": [], "warnings": [], "fix_instructions": [], "manual_override_risk": "high", "summary": "Below threshold."},  # noqa: ARG005
        )

        generate_draft(db, db.get(ArticleJob, job["id"]))
        run_human_edit(db, db.get(ArticleJob, job["id"]))
        run_qa(db, db.get(ArticleJob, job["id"]))

        job_row = db.get(ArticleJob, job["id"])
        assert job_row.status == "QA failed"

        result = set_manual_review_override(db, job_row, True)
        assert result["status"] == "Ready for review"
    finally:
        db.close()


def test_money_page_drafting_blocked_without_three_draft_ready_products():
    client = TestClient(app)
    job = _create_job(client, post_type="money_post")
    db = SessionLocal()
    try:
        _seed_brief(db, job["id"])
        db.add(
            CompetitorAnalysisReport(
                article_job_id=job["id"],
                dominant_intent="commercial investigation",
                recommended_angle="Practical guide",
            )
        )
        db.commit()
        response = client.post(f"/api/article-jobs/{job['id']}/generate-draft")
        assert response.status_code == 400
        assert "draft-ready product card" in response.json()["detail"]

        readiness = get_drafting_readiness(db, db.get(ArticleJob, job["id"]))
        assert readiness["can_generate_draft"] is False
        assert readiness["draft_ready_products"] == 0
    finally:
        db.close()


def test_full_workflow_stops_before_draft_when_product_readiness_fails(monkeypatch):
    # The automatic product_research step would otherwise call OpenAI web search.
    # Simulate discovery finding nothing, so the draft gate still blocks (graceful degrade).
    from app.services import product_research as _pr

    monkeypatch.setattr(_pr, "discover_products_via_websearch", lambda db, job, *, max_products=5: [])

    client = TestClient(app)
    article = _create_job(client, post_type="money_post")
    db = SessionLocal()
    try:
        _seed_brief(db, article["id"])
        db.add(
            KeywordResearch(
                article_job_id=article["id"],
                keyword="best dehumidifier",
                search_volume=100,
                source="DataForSEO",
            )
        )
        db.add(
            SerpResult(
                article_job_id=article["id"],
                keyword="best dehumidifier",
                position=1,
                title="Example",
                url="https://example.com",
                domain="example.com",
                result_type="organic",
            )
        )
        db.add(
            CompetitorAnalysisReport(
                article_job_id=article["id"],
                dominant_intent="commercial investigation",
                recommended_angle="Practical guide",
            )
        )
        db.add(
            CompetitorPage(
                article_job_id=article["id"],
                title="Example Competitor",
                url="https://example.com",
                domain="example.com",
                extraction_status="success",
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.post(
        f"/api/article-jobs/{article['id']}/run-full-workflow",
        json={"research_mode": "refresh_missing_only"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert "draft-ready product cards" in payload["summary_message"]
    statuses = {step["step_key"]: step["status"] for step in payload["steps"]}
    assert statuses["research_brief"] in {"complete", "skipped"}
    assert statuses["draft_generation"] == "skipped"
    assert statuses["human_edit"] == "skipped"
    assert statuses["qa"] == "skipped"

    db = SessionLocal()
    try:
        drafts = db.query(ArticleDraft).filter(ArticleDraft.article_job_id == article["id"]).count()
        assert drafts == 0
    finally:
        db.close()


def test_qa_fails_draft_below_minimum_word_count(monkeypatch):
    client = TestClient(app)
    job = _create_job(client, post_type="product_comparison")
    db = SessionLocal()
    try:
        _seed_brief(db, job["id"])
        openai_payloads = [
            {"score": 96, "passed": True, "failed_checks": [], "warnings": [], "fix_instructions": [], "manual_override_risk": "low", "summary": "Looks strong."},
            {"seo_title": "Title", "meta_description": "Meta", "slug": "slug", "excerpt": "Excerpt"},
        ]
        monkeypatch.setattr(OpenAIClient, "generate_json", lambda self, **kwargs: openai_payloads.pop(0))  # noqa: ARG005

        db.add(
            ArticleDraft(
                article_job_id=job["id"],
                version=1,
                stage="human_edit",
                draft_markdown="Short draft only.",
            )
        )
        db.commit()

        result = run_qa(db, db.get(ArticleJob, job["id"]), stage="initial")
        assert result["status"] == "QA failed"
        report = db.query(QaReport).filter(QaReport.article_job_id == job["id"]).order_by(QaReport.id.desc()).first()
        assert report is not None
        assert report.findings_json["minimum_word_count_passed"] is False
        assert "Minimum 1500 words required" in " ".join(report.findings_json["failed_checks"])
        qa_row = db.get(ArticleJob, job["id"])
        assert qa_row.current_qa_score == 84
    finally:
        db.close()


def test_qa_fails_overlong_support_style_informational_draft(monkeypatch):
    client = TestClient(app)
    job = _create_job(client, post_type="informational_blog")
    db = SessionLocal()
    try:
        _seed_brief(db, job["id"])
        openai_payloads = [
            {"score": 96, "passed": True, "failed_checks": [], "warnings": [], "fix_instructions": [], "manual_override_risk": "low", "summary": "Looks strong."},
            {"seo_title": "Title", "meta_description": "Meta", "slug": "slug", "excerpt": "Excerpt"},
        ]
        monkeypatch.setattr(OpenAIClient, "generate_json", lambda self, **kwargs: openai_payloads.pop(0))  # noqa: ARG005

        db.add(
            ArticleDraft(
                article_job_id=job["id"],
                version=1,
                stage="human_edit",
                draft_markdown=_complete_markdown("useful", 2800),
            )
        )
        db.commit()

        result = run_qa(db, db.get(ArticleJob, job["id"]), stage="initial")
        assert result["status"] == "QA failed"
        report = db.query(QaReport).filter(QaReport.article_job_id == job["id"]).order_by(QaReport.id.desc()).first()
        assert report is not None
        assert report.findings_json["maximum_word_count"] == 2200
        assert report.findings_json["maximum_word_count_passed"] is False
        assert "too broad" in " ".join(report.findings_json["failed_checks"])
    finally:
        db.close()


def test_build_context_exposes_cluster_target_as_primary_internal_cta():
    client = TestClient(app)
    job = _create_job(client, post_type="informational_blog")
    db = SessionLocal()
    try:
        cluster = ContentCluster(
            name=f"Mould Control {job['id']}",
            description="Support content for mould prevention.",
            target_url_slug="best-dehumidifier-for-mould-australia",
            notes="Main mould money page.",
        )
        db.add(cluster)
        db.commit()
        db.refresh(cluster)
        row = db.get(ArticleJob, job["id"])
        row.cluster_id = cluster.id
        db.add(row)
        _seed_brief(db, job["id"])
        db.commit()

        context = ad._build_context(db, row)

        assert context["internal_link_targets"]["primary_cta"]["url"] == "/best-dehumidifier-for-mould-australia/"
        assert context["internal_link_targets"]["primary_cta"]["source"] == "content_cluster.target_url_slug"
        assert context["internal_link_targets"]["cluster"]["name"] == f"Mould Control {job['id']}"
    finally:
        db.close()
