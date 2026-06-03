# Home Dry Lab Content Machine Agent Rules

## Scope
- Build local-first features first.
- Preserve clean service boundaries for DataForSEO, Anthropic Claude, OpenAI, and WordPress.
- Do not implement live external API calls unless explicitly requested in a separate task.

## Safety
- Never auto-publish WordPress content.
- WordPress export must only ever create drafts after explicit approval.
- Never expose secret values in logs, API responses, frontend payloads, screenshots, or tests.
- Never invent product specifications or testing claims.
- Never claim hands-on testing unless a product is marked as personally tested.
- Never delete or overwrite published WordPress content without explicit approval.
- Never expose `DATAFORSEO_LOGIN` or `DATAFORSEO_PASSWORD` to the frontend.
- All DataForSEO requests must be user-triggered from the UI or an explicit API call.
- Keep DataForSEO request volume controlled and log cost metadata safely.

## Architecture
- Keep the repository as a monorepo with `apps/web`, `apps/api`, `data`, and `docs`.
- Keep backend orchestration logic in services, not route handlers.
- Keep provider integrations behind dedicated service interfaces so each provider can be implemented independently.
- Prefer explicit schemas and typed payloads over loose dictionaries.

## Data
- SQLite is the local default.
- Migrations must remain runnable from the repo without Docker.
- Generated content, logs, and temporary research artefacts must stay local unless the user explicitly exports them.

## Frontend
- Never read secrets from the browser.
- Use API routes only for non-secret metadata such as settings validation state.
- Make job status and workflow state visible.

## Workflow
- Every workflow action should create an app log entry.
- Status changes must be explicit and traceable.
- Stubs should return placeholder metadata describing what a real integration will later do.

## Content Quality Rules

This app is not a generic AI article generator.

The purpose is to create high-quality Australian blog drafts for Home Dry Lab that are research-backed, useful, clear and human-sounding.

All generated content must:
- use Australian English
- avoid AI slop
- avoid fake expert wording
- avoid fake hands-on testing claims
- use research-backed claims only
- include product drawbacks
- include real buyer feedback patterns where available
- give clear decision-making help
- sound practical and human
- be suitable for WordPress draft review

The app must prioritise helpful content over keyword stuffing.

Never generate content that sounds like a generic affiliate article.
