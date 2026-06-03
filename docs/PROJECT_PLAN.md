# Project Plan

## Goal
Create a local-first content operations app that produces research-backed, Australian-style WordPress draft content for Home Dry Lab without auto-publishing.

## Phase 1
- Monorepo structure
- FastAPI backend with SQLite and Alembic
- Next.js frontend with CRUD surfaces
- Placeholder workflow actions for research, briefing, drafting, QA, and WordPress export
- Settings validation and safety-first logging

## Phase 2
- Claude and OpenAI drafting/review integrations
- Structured product evidence ingestion
- Rich QA scoring refinement and fix-pass automation
- WordPress draft export with approval workflow

## Current Foundation Additions
- Home Dry Lab content quality system
- Editable content rules and QA gating
- Live DataForSEO v3 SERP research integration
- Live DataForSEO v3 keyword idea integration
- Safe request, app log, and cost log handling for research workflows

## Non-goals For Phase 1
- No live third-party API calls
- No auto-publish behavior
- No production deployment automation
