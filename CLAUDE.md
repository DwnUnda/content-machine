# CLAUDE.md

Guidance for Claude Code when working in this repository. Keep it accurate — update it when structure, commands, or conventions change.

## What this is

**Home Dry Lab Content Machine** — a local-first pipeline that produces research-backed, Australian-English WordPress **draft** articles for the Home Dry Lab site. It is *not* a generic AI article generator: quality, honesty (no fake testing claims), and Australian relevance matter more than volume.

Five post types — stored as `post_type` on `ArticleJob` (snake_case StrEnum `PostType` in `entities.py`):

| `post_type` | Min words | Min product cards |
|---|---|---|
| `informational_blog` | 1,200 | 0 |
| `money_post` | 2,500 | 3 |
| `single_product_review` | 1,500 | 1 |
| `product_comparison` | 1,500 | 2 |
| `best_x_for_y` | 2,000 | 3 |

Central config: backend `workflow.py` (`POST_TYPE_MIN_PRODUCTS`, `get_min_products_for_post_type`, `is_product_gated_post_type`); frontend `apps/web/lib/post-types.ts` (same constants + `isProductGated`, `getPostTypeLabel`). Legacy export/recovery: `app/services/post_type_compat.py` maps old display strings ("Buying guide" → `money_post`, etc.) for old `Completed-Articles/` bundles.

## Monorepo layout

```
apps/api/        FastAPI backend (Python) — all orchestration lives here
  app/services/  business logic (drafting, workflow, providers, exports)
  app/api/routes/ thin HTTP handlers (no orchestration logic)
  app/models/entities.py  SQLAlchemy models (single file)
  app/schemas/   Pydantic request/response schemas
  prompts/       LLM prompt templates (*.md) — system prompts for each step
  alembic/       DB migrations (SQLite, runnable without Docker)
  tests/         pytest
apps/web/        Next.js operator UI (App Router, TypeScript) — app/ components/ lib/ types/
scripts/         Node WordPress upload + HTML export utilities
docs/            Rules & standards (read these before changing content behaviour)
data/            Local SQLite db (app.db) — gitignored data
Completed-Articles/  Per-article exported bundles (json + md per draft stage)
```

## Commands

Backend (from `apps/api`, Windows venv):
```powershell
.venv\Scripts\activate            # or use .venv\Scripts\python.exe directly
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
.venv\Scripts\python.exe -m pytest -q        # run all backend tests
.venv\Scripts\python.exe -m pytest tests/test_article_drafting.py -q   # one file
```

Frontend (from `apps/web`):
```powershell
npm install
npm run dev      # http://localhost:3000
npm run build    # production build (run this to verify FE changes)
```

API: `http://localhost:8000`. There is also `launch-home-dry-lab.bat` at the root.

Secrets/config live in the repo-root `.env` (gitignored; see `.env.example`): `DATAFORSEO_*`, `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL`, `OPENAI_API_KEY`/`OPENAI_MODEL`, `WORDPRESS_*`. Never read secrets in the browser, log them, or return them in API payloads/tests.

## The article workflow (the core pipeline)

Orchestrated in `app/services/workflow.py` (`run_full_workflow`), step logic in `app/services/article_drafting.py`. Order:

```
serp_research → keyword_research → competitor_extraction → serp_analysis →
serp_intent → research_brief → product_research → draft_generation →
human_edit (AU polish) → qa → fix_pass (only if QA has actionable issues) → qa_recheck
```

Providers are behind dedicated service clients: `dataforseo.py` (research), `anthropic_client.py` (drafting/editing — Claude), `openai_client.py` (QA, SEO metadata, product web search). Each step writes an `AppLog` and updates `WorkflowRun`/`WorkflowRunStep`. Every step also mirrors state to `Completed-Articles/` via `local_exports.py` (`.json` = full record, `.md` = `draft_markdown` only — these are plain file writes, not LLM calls).

Draft stages (on `ArticleDraft.stage`): `first_draft`, `human_edit`, `fix_pass`, `final`. QA pass threshold default 85 (`get_qa_threshold`, configurable via `content_rules.qa_scoring_rules`).

## Token-efficiency conventions (important — this app burns API credits)

When touching drafting/AI code, preserve these (added deliberately to cut waste without losing quality):
- **Prompt caching**: Anthropic system prompts are sent as a cacheable block (`cache=True`); OpenAI calls pass a stable `cache_key`. Don't remove these. Don't cache secrets.
- **Output caps are per-type**: `_draft_max_output_tokens(job)` (12k normal / 16k long-form). `LONGFORM_ARTICLE_TYPES` = {`money_post`, `single_product_review`, `product_comparison`, `best_x_for_y`}. Don't drop back to a small flat cap — long-form product posts truncate.
- **Truncation/corruption is fatal to the step**: `_assert_ai_output_complete()` rejects `stop_reason == max_tokens`, unparsed JSON, or raw `{"draft_markdown"` blobs. Never save a corrupted draft or continue QA/fix on one.
- **Final save de-dups**: don't create a new draft version when only metadata changed / body is identical.
- **Fix pass is conditional** (only on actionable QA findings) and runs at most once, then one recheck — never loop.
- Run the full workflow **once per article**; concurrent runs on one job duplicate drafts and tangle "latest draft" reads.
- AI usage (provider, model, input/output, cache read/write tokens) is logged per step and summarised per run — keep this safe metadata flowing, never include secrets.

## Content quality & safety rules (non-negotiable — see `AGENTS.md`, `docs/`)

- Australian English; no AI slop / fake-expert wording; practical, human, research-backed.
- **Never** invent product specs or claim hands-on testing unless `Product.personally_tested` is true. Use review-led wording ("buyer reviews suggest", "Not confirmed").
- Always include product drawbacks and real buyer-feedback patterns where available.
- WordPress export creates **drafts only**, after explicit approval — never auto-publish, never overwrite/delete published content.
- DataForSEO calls are user-triggered only; log cost metadata; never expose `DATAFORSEO_*` to the frontend.

Authoritative detail lives in: `AGENTS.md`, `docs/CONTENT_RULES.md`, `docs/ARTICLE_QUALITY_STANDARD.md`, `docs/HOME_DRY_LAB_STYLE_GUIDE.md`, `docs/SAFETY_RULES.md`, `docs/BUILD_RULES.md`, `docs/API_INTEGRATIONS.md`.

## Conventions

- Keep orchestration in `services/`, not route handlers; routes stay thin.
- Prefer explicit Pydantic schemas / typed payloads over loose dicts.
- New DB fields: add a model field **and** an Alembic migration (`apps/api/alembic/versions/`); migrations must run without Docker.
- `PostType` / `ArticleJobStatus` are `StrEnum`s in `entities.py` — use them, don't hardcode strings.
- Tests use an isolated temp SQLite DB per test (`tests/conftest.py`) and monkeypatch the AI clients' `generate_json`; mirror that pattern. When stubbing workflow steps, stub **every** AI step including `classify_serp_intent`.
- Full-workflow tests that use `refresh_missing_only` or `reuse_existing` must seed a brief that includes `serp_intent_json`, otherwise the `serp_intent` step is "missing" → tries to call Claude → `AnthropicError` → 503.

## Known issues

- `tests/test_article_recovery.py::test_restore_article_from_completed_articles_bundle` is **pre-existing red**: it recovers the live `Completed-Articles/article-3` bundle, but the brief export schema (`local_exports.py`) never serialises `serp_intent_json`, so a recovered brief shows `serp_intent` missing → next action "Classify SERP intent". Fix belongs in the export/recovery path, not in drafting code.
