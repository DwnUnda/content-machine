# SEO Metadata Prompt

Create SEO metadata for a Home Dry Lab draft.

The article's primary keyword is provided in `article_context.article_job.primary_keyword`
(and `article_context.research_brief.primary_keyword`). Use it to satisfy basic
Rank Math SEO checks — but do this naturally. Practical SEO, not spam.

Requirements:
- Australian English
- practical, natural phrasing
- no hype language
- no fake certainty
- align with article intent

Primary keyword usage (natural, not forced):
- `seo_title`: include the primary keyword or a close exact variation, naturally.
  Keep it clean and search-intent focused. Do NOT force clickbait.
  Example primary keyword "how long should you run a dehumidifier" →
  good title "How Long Should You Run a Dehumidifier?".
- `meta_description`: include the primary keyword or a close variation, readable
  and useful. Do NOT keyword stuff.
- `slug`: base it on the primary keyword where possible
  (e.g. "how-long-should-you-run-a-dehumidifier"). Lowercase, hyphenated, no stop-word padding.
- Numbers, power words, and emotional sentiment are OPTIONAL. Only use a number
  if the title naturally supports one. Never force
  "7 Powerful Reasons You Must Run a Dehumidifier Longer"-style titles.

Return:
- `seo_title`
- `meta_description`
- `slug`
- `excerpt`
- `social_summary`

Output format:
- Return JSON only.
- Do not wrap the JSON in code fences.
