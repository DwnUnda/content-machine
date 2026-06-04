# Editor Correction Prompt

Apply the editor's correction notes to the current Home Dry Lab draft.

You are revising an existing draft, not starting from scratch.

Rules:
- Preserve the source format of the input draft. If it is HTML, return clean
  HTML only. If it is Markdown, return Markdown only.
- Apply the editor notes as the highest-priority instruction unless they would
  require unsupported claims, fake product facts, fake testing claims, unsafe
  advice, or invented URLs.
- Do not invent product specifications, prices, warranties, ratings, review
  counts, source links, affiliate links, or internal URLs.
- Keep Australian English.
- Preserve useful existing content that still fits the requested correction.
- Remove, merge, or rewrite sections that the editor says are bloated,
  off-topic, repetitive, or misaligned with the keyword.
- If the correction asks for internal links, use only provided
  `internal_link_targets`; if no real target exists, add no link.
- If the correction asks for product images, use only `product_image_url` values
  already present in product data. Otherwise keep placeholders.
- Do not add inline CSS, JavaScript, `<html>`, `<head>`, or `<body>` tags.
- Return the complete revised draft only, not JSON, a patch, an excerpt, or
  commentary.
