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
