# API Integrations

## Planned Providers

### DataForSEO
- Use for SERP collection, ranking competitors, and keyword research.
- Implemented service boundary: `app/services/dataforseo.py`
- API version: DataForSEO API v3 only
- Authentication: HTTP Basic Auth using `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD`
- Current endpoints used:
  - `POST /v3/serp/google/organic/live/advanced`
  - `POST /v3/keywords_data/google_ads/keywords_for_keywords/live`
- Current target market defaults:
  - Location: Australia (`location_code=2036`)
  - Language: English
- Safety rules:
  - Never expose credentials to the frontend
  - Never log credentials
  - Only run calls from explicit user-triggered workflow actions
  - Keep SERP depth capped at 10 by default
- Cost logging:
  - Write `cost_logs` entries for `serp_research` and `keyword_research`
  - Store endpoint path and request count in notes
  - Store USD cost when DataForSEO returns it, else store `null`

### Anthropic Claude
- Use for brief refinement, long-form drafting, and editorial rewrites.
- Future service boundary: `app/services/integrations/anthropic_client.py`

### OpenAI
- Use for drafting support, structured extraction, classification, and QA enrichment.
- Future service boundary: `app/services/integrations/openai_client.py`

### WordPress REST API
- Use only for authenticated draft export after explicit approval.
- Future service boundary: `app/services/integrations/wordpress.py`

## Integration Rules
- Keep provider-specific request and response mapping out of route handlers.
- Log action summaries without storing secrets.
- Store provider cost and usage in `cost_logs`.
- Preserve raw provider payload storage only when explicitly needed and safe.
- On DataForSEO failures, return safe errors without auth details or raw secrets.
