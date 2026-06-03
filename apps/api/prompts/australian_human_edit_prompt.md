# Australian Human Edit Prompt

Rewrite the draft so it reads like a useful Australian article from Home Dry Lab.

Focus on:
- Australian English spelling and phrasing
- Plainer and more natural wording
- Removing AI-slop transitions
- Tightening fake-expert or over-polished language
- Keeping practical decision help
- Preserving evidence-backed claims only
- Preserving uncertainty where facts are not confirmed
- If there are no linked product cards or no source-backed product facts, do not invent model-level specs from competitor pages.
- Keep product recommendations at category level when product facts are missing and use `Not confirmed` instead of guessing.
- Follow `product_policy` exactly. If linked product cards are unavailable, do not promote any named product.
- Keep the article complete. If the source draft already has FAQ or final recommendation sections, preserve them and finish any truncated ending.
- Do not shorten the article so much that the FAQ or final recommendation disappears.
- Remove internal workflow notes from the reader-facing copy. Do not mention competitor pages, linked product cards, hidden workflow state, or backend-only flags in the public article.
- If you mention research or methodology, keep it short and human. Do not expose backend labels like `Not confirmed` unless they are needed in a reader-facing explanation.

Do not:
- add invented facts
- add fake testing claims
- turn it into hype copy
- remove drawbacks or cautions
- promote product specs that are not confirmed

Testing-claim guardrail (hard rule):
- Do not introduce or keep first-hand testing language (`We tested`, `In our lab`,
  `During our hands-on review`, `Our testing found`) for any product whose
  `personally_tested` flag is not `true`. Rewrite such claims into review-led wording
  like `Based on customer feedback`, `Users commonly report`, `Reviewers often
  mention`, `Across customer reviews, the recurring theme is`, or `Product specs
  suggest`.
- Preserve a `How we chose these products` methodology section if the draft has one;
  do not turn it into a testing claim unless every featured product is
  `personally_tested=true`.

Output format:
- Return JSON only.
- Use this shape:
  - `draft_markdown`: the rewritten article in the same source format it was given
  - `notes`: a short array of edit notes
  - `content_modules`: preserve or update the major renderer modules present in the article using objects like
    `{"module_type":"comparison","heading":"Quick comparison"}`
- Preserve the source format of the input draft. If the draft is HTML, return HTML. If the draft is markdown, return markdown.
- The article must remain complete and end with a finished final recommendation section after the FAQ.
- Do not wrap the JSON in code fences.
