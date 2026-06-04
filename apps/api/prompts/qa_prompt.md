# Home Dry Lab QA Prompt

Review the article against the Home Dry Lab quality standard.

Score these areas:
- Australian English
- no fake testing claims
- no unsupported specs
- no AI slop phrases
- clear search intent match
- clear recommendations
- product drawbacks included
- Australian context included
- evidence-backed claims
- internal links reviewed before publishing
- readable formatting
- original value included

Hard rule:
- If the draft names specific product models or specs but `products` is empty or `products_available` is false, treat that as unsupported product claims and score it down heavily.
- If product cards are unavailable, the draft should stay at category level and use `Not confirmed` for missing product facts.

Required and optional block coverage:
- The input may include `serp_intent` with `required_blocks` and `optional_blocks`.
  These describe blocks the article should contain to satisfy the searcher.
- Check whether each `required_block` is meaningfully present in the draft.
  A missing REQUIRED block is a real quality gap: add it to `failed_checks` and
  lower the score. Do not fail solely because a block is named differently —
  judge whether the substance is present (e.g. a running-cost formula, a decision
  table, a "how to know it worked" section).
- A missing `optional_block` is a `warnings` item only. Never fail QA for a missing
  optional block.
- Do NOT reward padding. A block only counts if it adds genuine, specific value.

Content density rule:
- Do not reward length by itself.
- For informational_blog drafts, judge whether the page is a focused support
  article or a true pillar guide. Direct question/problem keywords should usually
  be support articles, not broad mega-guides.
- For support-style informational drafts, add a warning if the article feels
  over 2,000 words, has too many H2 sections, or covers buyer-guide/rental/cost
  topics in more depth than the core query needs.
- For support-style informational drafts, treat excessive breadth as a failed
  check when it makes the page compete with a money page instead of routing
  readers toward it.
- Support-style informational FAQs should usually have 4-6 questions. Warn when
  the FAQ repeats the body or becomes a second article.
- If table-like content is flattened as plain text instead of a real table,
  flag it as a formatting issue.
- For commercial drafts, flag repeated advice across top picks, product reviews,
  buyer guides, mistakes, FAQs and final recommendations.
- Add a warning if a commercial draft feels padded, if the FAQ is oversized, or
  if product reviews repeat comparison-table points without adding useful buyer
  evidence, drawbacks or fit notes.
- Add a warning if a money_post or best_x_for_y draft exceeds about 5,800 words
  without a clear brief-driven reason.
- Add a warning if commercial product review sections feel like mini blog posts
  rather than concise buying decisions.
- Add a warning if the final verdict is long enough to re-explain the article
  instead of giving a short decision summary.
- Add a warning if the draft has long uninterrupted prose blocks with no table,
  list, spec box, pros/cons block, decision box, CTA box, callout, image or
  product placeholder.
- Treat excessive repetition as a failed check when it makes the draft harder to
  use, buries recommendations, or creates a generic affiliate-article feel.
- Prefer concise sections with clear decision value over exhaustive coverage.

Informational support article rule:
- For informational_blog drafts with a direct question or problem-solving intent,
  evaluate product guidance at support-article depth. It is enough to explain
  when a product category helps, when it will not solve the problem, and the
  few category-level factors that matter.
- Do not require full buyer-guide specs, product rankings, product reviews, or
  detailed buying sections for informational_blog support articles unless the
  brief explicitly asks for a pillar guide or buyer guide.
- Missing deep product detail should be a warning, not a failed check, when the
  article is otherwise focused and routes readers toward a relevant buying
  guide or future internal-link opportunity.
- Continue to fail unsupported specific product models, invented specs, fake
  test claims, or confident health/safety claims without evidence.

Internal link rule for this stage:
- Treat the current QA run as draft-generation QA unless the input explicitly says publish-ready or final-publish mode.
- If the draft has no internal links and no internal link suggestions, do not fail QA for that alone. Add a warning only.
- Use this warning wording when relevant: "No internal links were included. This is acceptable for draft generation, but internal link opportunities should be reviewed before publishing once related content exists."
- If related content clearly exists, you may suggest internal link opportunities, but missing internal links should still be a warning, not a major failure, during draft-generation QA.
- Do not invent internal URLs, fake slugs, `#` links, `/coming-soon` links, or other placeholder links to satisfy the check.
- Only treat internal linking as a true failure if the input explicitly requires publish-ready content, or if the article contains broken or placeholder internal links that would be unsafe to publish.

Return:
- numeric score out of 100 as `score`
- pass/fail against 85 threshold as `passed`
- issue list with severity as `failed_checks`
- warnings as `warnings`
- a short `summary`

Output format:
- Return JSON only.
- Do not wrap the JSON in code fences.
- Keep the JSON compact and concise.
- Return only these keys: `score`, `passed`, `failed_checks`, `warnings`, `summary`.
- Do not include rewritten article text.
- Do not include long explanations.
- Keep each failed check or warning short and specific.
