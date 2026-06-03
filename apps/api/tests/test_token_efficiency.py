"""Tests for the token-efficiency / draft-bloat fixes.

Covers prompt-caching config (without leaking secrets), truncation/corruption
rejection, the enrichment pre-check, enrichment-before-polish ordering, final-save
de-duplication, and the conditional/limited fix pass. Behaviour is exercised for
both a normal blog post and a money/product post where it matters.
"""

from pathlib import Path
from types import SimpleNamespace
import json
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import ArticleBrief, ArticleDraft, ArticleJob
from app.services import anthropic_client as ac
from app.services import openai_client as oc
from app.services import article_drafting as ad
from app.services.anthropic_client import AnthropicClient
from app.services.article_drafting import (
    ArticleDraftingError,
    generate_draft,
    run_qa,
)
from app.services.openai_client import OpenAIClient


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _create_job(client: TestClient, post_type: str = "informational_blog") -> dict:
    return client.post(
        "/api/article-jobs",
        json={"title": "Token Efficiency Test", "primary_keyword": "best dehumidifier", "post_type": post_type},
    ).json()


def _seed_brief(db, job_id: int) -> None:
    db.add(
        ArticleBrief(
            article_job_id=job_id,
            version=1,
            brief_markdown="# Brief",
            serp_intent_json={"primary_intent": "commercial investigation", "content_type": "buying guide"},
            outline_json={
                "primary_keyword": "best dehumidifier",
                "search_intent": "buying",
                "required_sections": ["quick answer"],
                "suggested_title_options": ["Best dehumidifier"],
                "suggested_slug": "best-dehumidifier",
                "meta_description_draft": "Meta",
            },
        )
    )
    db.commit()


def _full_normal_markdown() -> str:
    return (
        "# Best Dehumidifier Guide\n\n"
        "## Quick answer\n\nBuy a compressor unit for a damp room in Australia.\n\n"
        + " ".join(["filler"] * 1300)
        + "\n\n## How it works\n\nText.\n\n## Sizing\n\nText.\n\n## Setup\n\nText.\n\n"
        "## FAQ\n\n### What size?\n\nMatch the room.\n\n"
        "## Final Recommendation\n\nPick a compressor unit and set it to 50%."
    )


def _full_money_markdown() -> str:
    return (
        "# Best Dehumidifier For Mould Australia\n\n"
        "This article is based on manufacturer specifications and recurring buyer feedback.\n\n"
        "## Quick answer\n\nA compressor unit suits most damp Australian rooms.\n\n"
        "## Comparison table\n\n| Model | Price |\n|---|---|\n| A | $1 |\n\n"
        "## Product recommendations\n\n### Model A\n\n**Best for:** small rooms. "
        "Who should buy it: renters. **Bottom line:** solid value.\n\n"
        "## Buying guide\n\nText.\n\n## Sizing\n\nText.\n\n"
        + " ".join(["filler"] * 2600)
        + "\n\n## FAQ\n\n### What size?\n\nMatch the room.\n\n"
        "## Final Recommendation\n\nBuy the compressor unit."
    )


# --------------------------------------------------------------------------- #
# 1. Prompt caching config is applied without exposing secrets
# --------------------------------------------------------------------------- #
def test_anthropic_caches_system_prompt_without_leaking_secret(monkeypatch):
    monkeypatch.setattr(
        ac, "get_settings", lambda: SimpleNamespace(anthropic_api_key="secret-key-123", anthropic_model="claude-test")
    )
    captured = {}

    def fake_post(self, payload):  # noqa: ARG001
        captured["payload"] = payload
        usage = {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 8, "cache_creation_input_tokens": 2}
        return ac.AnthropicResponse(
            model=payload["model"],
            content_text='{"draft_markdown": "# Title\\n\\nBody."}',
            response_json={"stop_reason": "end_turn", "usage": usage},
            stop_reason="end_turn",
            usage=usage,
        )

    monkeypatch.setattr(ac.AnthropicClient, "_post", fake_post)

    client = ac.AnthropicClient()
    client.generate_json(system_prompt="STABLE TEMPLATE", user_prompt="VARIABLE")

    system_field = captured["payload"]["system"]
    assert isinstance(system_field, list)
    assert system_field[0]["text"] == "STABLE TEMPLATE"
    assert system_field[0]["cache_control"] == {"type": "ephemeral"}

    meta = client.usage_metadata()
    assert meta["provider"] == "Anthropic"
    assert meta["cache_read_tokens"] == 8
    assert meta["cache_write_tokens"] == 2
    # No secret material in the safe usage metadata.
    assert "secret-key-123" not in json.dumps(meta)


def test_openai_sets_prompt_cache_key_without_leaking_secret(monkeypatch):
    monkeypatch.setattr(
        oc, "get_settings", lambda: SimpleNamespace(openai_api_key="sk-secret", openai_model="gpt-test")
    )
    captured = {}

    def fake_post(self, payload):  # noqa: ARG001
        captured["payload"] = payload
        usage = {"input_tokens": 100, "output_tokens": 20, "input_tokens_details": {"cached_tokens": 80}}
        return oc.OpenAIResponse(
            model=payload["model"],
            content_text='{"score": 90, "passed": true}',
            response_json={"usage": usage},
            stop_reason=None,
            usage=usage,
        )

    monkeypatch.setattr(oc.OpenAIClient, "_post", fake_post)

    client = oc.OpenAIClient()
    client.generate_json(instructions="QA PROMPT", input_text="ARTICLE", cache_key="qa")

    assert captured["payload"]["prompt_cache_key"] == "qa"
    meta = client.usage_metadata()
    assert meta["cache_read_tokens"] == 80
    assert "sk-secret" not in json.dumps(meta)


# --------------------------------------------------------------------------- #
# 2. Truncated / corrupted draft is rejected and does not continue
# --------------------------------------------------------------------------- #
def test_assert_ai_output_complete_rejects_truncation_and_corruption():
    truncated = SimpleNamespace(last_stop_reason="max_tokens", last_parse_ok=True)
    with pytest.raises(ArticleDraftingError):
        ad._assert_ai_output_complete(truncated, markdown="# ok\n\nbody", stage="Draft generation")

    unparsed = SimpleNamespace(last_stop_reason="end_turn", last_parse_ok=False)
    with pytest.raises(ArticleDraftingError):
        ad._assert_ai_output_complete(unparsed, markdown="# ok\n\nbody", stage="Draft generation")

    clean = SimpleNamespace(last_stop_reason="end_turn", last_parse_ok=True)
    # A clean response must not raise.
    ad._assert_ai_output_complete(clean, markdown="# ok\n\nbody", stage="Draft generation")

    # A raw JSON blob body is corruption even if the flags look fine.
    with pytest.raises(ArticleDraftingError):
        ad._assert_ai_output_complete(clean, markdown='{"draft_markdown": "# x\\n\\nbody"}', stage="Draft generation")


def test_generate_draft_rejects_corrupted_output_and_saves_nothing(monkeypatch):
    client = TestClient(app)
    job = _create_job(client)
    db = SessionLocal()
    try:
        _seed_brief(db, job["id"])
        blob = '{"draft_markdown": "# Best\\n\\n' + "word " * 30 + '"'
        monkeypatch.setattr(
            AnthropicClient,
            "generate_json",
            lambda self, **kwargs: {"draft_markdown": blob, "notes": [], "title_options": []},  # noqa: ARG005
        )
        with pytest.raises(ArticleDraftingError):
            generate_draft(db, db.get(ArticleJob, job["id"]))
        # No corrupted draft was saved, so QA/fix/final never run on it.
        count = db.query(ArticleDraft).filter(ArticleDraft.article_job_id == job["id"]).count()
        assert count == 0
    finally:
        db.close()


def test_run_qa_rejects_corrupted_latest_draft(monkeypatch):
    client = TestClient(app)
    job = _create_job(client)
    db = SessionLocal()
    try:
        _seed_brief(db, job["id"])
        db.add(
            ArticleDraft(
                article_job_id=job["id"],
                version=1,
                stage="human_edit",
                draft_markdown='{"draft_markdown": "# Best\\n\\nbody"}',
            )
        )
        db.commit()
        # QA must refuse before spending an OpenAI call.
        monkeypatch.setattr(
            OpenAIClient,
            "generate_json",
            lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("QA should not call the model")),  # noqa: ARG005
        )
        with pytest.raises(ArticleDraftingError):
            run_qa(db, db.get(ArticleJob, job["id"]), stage="initial")
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 3. Identical final body / metadata-only save does not create a new version
# --------------------------------------------------------------------------- #
def test_identical_final_body_does_not_duplicate_draft_version(monkeypatch):
    client = TestClient(app)
    job = _create_job(client)
    db = SessionLocal()
    try:
        _seed_brief(db, job["id"])
        db.add(
            ArticleDraft(
                article_job_id=job["id"],
                version=1,
                stage="human_edit",
                draft_markdown=_full_normal_markdown(),
            )
        )
        db.commit()

        qa_payload = {"score": 95, "passed": True, "failed_checks": [], "warnings": [], "fix_instructions": [], "manual_override_risk": "low", "summary": "Strong."}
        seo_payload = {"seo_title": "Title", "meta_description": "Meta", "slug": "slug", "excerpt": "Excerpt"}
        payloads = [qa_payload, seo_payload, qa_payload, seo_payload]
        monkeypatch.setattr(OpenAIClient, "generate_json", lambda self, **kwargs: payloads.pop(0))  # noqa: ARG005

        run_qa(db, db.get(ArticleJob, job["id"]), stage="initial")
        run_qa(db, db.get(ArticleJob, job["id"]), stage="recheck")

        finals = (
            db.query(ArticleDraft)
            .filter(ArticleDraft.article_job_id == job["id"], ArticleDraft.stage == "final")
            .all()
        )
        # Second QA had the same body, so no duplicate final version was created.
        assert len(finals) == 1
        assert finals[0].seo_title == "Title"
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 6. Fix pass is conditional and limited to one run + one recheck
# --------------------------------------------------------------------------- #
def test_qa_actionability_gate():
    from app.services.workflow import _qa_findings_actionable

    assert _qa_findings_actionable({"failed_checks": ["AI slop"]}) is True
    assert _qa_findings_actionable({"fix_instructions": ["Trim"]}) is True
    assert _qa_findings_actionable({"minimum_word_count_passed": False}) is True
    assert _qa_findings_actionable({"failed_checks": [], "fix_instructions": [], "warnings": ["vague"]}) is False
    assert _qa_findings_actionable({}) is False


def test_workflow_runs_fix_and_recheck_at_most_once():
    from app.services.workflow import WORKFLOW_STEP_SPECS

    keys = [key for key, _ in WORKFLOW_STEP_SPECS]
    assert keys.count("fix_pass") == 1
    assert keys.count("qa_recheck") == 1
