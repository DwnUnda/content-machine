from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared rendering rules injected into every post type block.
# ---------------------------------------------------------------------------
_RENDERING_RULES = """
## Rendered HTML rules (all post types)

Every article type must be renderable into polished HTML before local export or
WordPress upload. The draft source format depends on the post type rules below.

When a post type says `Source format: HTML`:
- Return clean HTML in the `draft_markdown` field — suitable for direct use as
  WordPress post content.
- Do NOT include:
- <html>, <head>, or <body> tags
- inline CSS style attributes
- JavaScript
- markdown syntax (##, **, __, etc.)
- code fences (```)

When a post type says `Source format: Markdown`:
- Return normal markdown in the `draft_markdown` field.
- Do NOT wrap the article in raw HTML.
- Use standard markdown headings, lists, links, tables, and paragraphs only.
- Do not embed inline CSS, JavaScript, or ad-hoc HTML layout wrappers.

Rendered HTML should use semantic structure:
- <article> as the outermost wrapper
- <section> for major content blocks
- <h1>, <h2>, <h3> for headings
- <p> for paragraphs (keep them short — 3–4 sentences max)
- <ul> / <ol> for lists
- <table> for comparison or spec data
- <aside> for callout boxes where appropriate

Use stable CSS classes from the class system below when the post type outputs
HTML directly. Do not add custom or ad-hoc class names.

Required CSS classes (use exactly these, not variations):
  Article wrappers: money-post | informational-post | single-product-review |
                    product-comparison-post | best-x-for-y-post
  Hero sections:    money-hero | review-hero | comparison-hero
  Cards & badges:   product-card | featured | badge | top-picks-grid |
                    hero-summary | product-image-wrap |
                    product-image-placeholder | read-review-link
  CTAs:             cta-button | button | cta-box
  Tables:           comparison-table | table-wrap | table-cta
  Decision modules: decision-box | decision-grid | use-case-decision-box
  Product blocks:   product-reviews | product-review | product-header |
                    product-layout | product-main | product-sidebar |
                    pros-cons | spec-box
  Editorial:        methodology-box | buyer-guide | mistakes-section |
                    faq-section | final-verdict | education-section |
                    comparison-section | winner-by-use-case |
                    problem-context-section | performance-section |
                    specs-section | pros-cons-section | review-summary-box |
                    jump-links | hdl-toc

Do not include empty or placeholder sections. If source data for a section is
unavailable, write a short honest caveat instead of fabricating content.

Do NOT claim first-hand testing unless explicitly provided in the product data
(personally_tested=true for that specific product).

Do NOT invent product prices, specs, warranties, ratings, or review counts.

Do NOT invent affiliate URLs. Use this placeholder for every CTA button:
  <a class="button cta-button" href="#" data-product="PRODUCT_NAME">Check latest price</a>
If a product URL is present in the product data, use that URL instead of "#".

Commercial content-density rules:
- For money_post and best_x_for_y drafts, aim for roughly 4,000-5,200 words.
  Do not exceed about 5,800 words unless the brief clearly requires a deeper
  guide.
- For product_comparison and single_product_review drafts, keep the page
  commercially complete but tighter than a broad buyer guide.
- The first answer, top picks, comparison table and use-case split carry the
  buyer intent. Supporting sections must add new decision value, not restate
  the same recommendation logic.
- Product review blocks inside money_post and best_x_for_y drafts should be
  concise: about 350-500 words per product, excluding spec tables. Use only the
  evidence, drawbacks and fit notes that change the buying decision.
- FAQ sections should use 6-8 high-intent questions with short answers. Do not
  repeat the buyer guide or product reviews.
- Final recommendations should be 150-250 words and should not recap every
  product in full.
- Do not run more than 250-350 words of prose, or more than 3 standard
  paragraphs, without a scannable module such as a table, list, spec box,
  pros/cons block, decision box, CTA box, callout or product image placeholder.
- If a section adds no new decision-making value, merge it, shorten it or omit
  it.
- Broad category money pages (`article_job.commercial_page_scope` =
  `broad_category_money_page`, e.g. "best dehumidifier Australia") need wider
  product coverage than narrow use-case pages: use 8-10 products when that many
  draft-ready product cards are available. Narrow use-case pages should stay
  more selective.
- For broad category money pages, include a "Best by use case" or equivalent
  decision section near the top that maps the category to concrete buyer
  situations (budget, bedroom, bathroom, mould, laundry drying, large room,
  compact/small-space, quiet, premium) when supported by product data.
- For long commercial buyer guides, include a compact visible table of contents
  block using `<nav class="hdl-toc" aria-label="In this guide">`. Put the
  buying answer first, then the TOC; do not make buyers scroll through
  navigation before seeing recommendations.
- Use provided internal_link_targets only. Add contextual internal links when
  real targets exist, but never invent site URLs.
- Add visible source/reference links where product claims depend on a
  manufacturer page, retailer page, review page, or running-cost assumption.
"""

# ---------------------------------------------------------------------------
# Per-post-type generation rules
# ---------------------------------------------------------------------------
_INFORMATIONAL_BLOG_RULES = """
## Post type: informational_blog

Source format: Markdown

Generate a focused informational SEO blog post. This is NOT a buyer guide —
do not include product cards, aggressive CTAs, or full buyer-decision frameworks
unless the keyword specifically demands product recommendations.

Most informational_blog drafts for Home Dry Lab are support articles: they answer
one practical search intent clearly, then route readers toward the most relevant
commercial guide or deeper support article. Do not turn a support article into a
mini pillar page unless the brief, SERP intent or user notes explicitly request a
comprehensive pillar guide.

Purpose:
- Answer the search intent clearly.
- Educate the reader.
- Build topical authority on the site.
- Support internal linking to related commercial pages where relevant.
- Feed money pages without competing with them.

Rendered HTML wrapper target:

<article class="informational-post">...</article>

Required markdown structure:

# [TITLE]

[SHORT INTRO — 2–3 sentences. For question/problem keywords, answer the main
question within the first 150 words.]

## Short answer
[DIRECT ANSWER — practical, plain-English, no bloated setup]

[RELATED_BUYING_GUIDE marker — include only when `internal_link_targets.primary_cta`
is present in the input context. Use exactly this single-line marker format:
[[RELATEDBUYINGGUIDE|Need help choosing?|One short sentence explaining the
related buying guide.|/target-slug/|View the guide]]]

## [Main topic / first subtopic]
[CONTENT]

## [Second subtopic]
[CONTENT]

## [Additional subtopics as needed]
[CONTENT]

## Frequently asked questions
[FAQ ITEMS — include if search intent is informational or navigational]

## Final thoughts
[CONCLUSION — practical summary, not a sales pitch]

Support article length and scope:
- For direct question, problem-solving, troubleshooting, cost, health-adjacent,
  rental, or "does/how/when/what" keywords, treat the draft as a support article
  unless the brief explicitly asks for a pillar guide.
- Support articles should usually be 1,200-2,000 words, ideally around
  1,500-1,800 words.
- Do not exceed about 2,200 words for a support article unless the user notes,
  SERP intent, or brief explicitly request a comprehensive/pillar guide.
- Use about 5-8 H2 sections for support articles. If the outline wants more,
  merge related sections.
- FAQ sections in support articles should use 4-5 questions max with short
  answers.
- Compress sizing, running-cost, product-choice, rental, seasonal, and buying
  guidance unless those are the primary keyword intent.
- If buying guidance is relevant, summarise it briefly and link to the related
  buying guide instead of becoming a buyer guide.
- Avoid repeating the same point across the body, FAQ and conclusion.
- For yes/no keywords such as "will a dehumidifier remove existing mould" or
  "does a dehumidifier help with mould", do not create standalone sections for
  running costs, rental law, climate zones, product sizing, or buying criteria.
  Mention those only briefly when they directly affect the answer, then route to
  a related guide when a real internal target exists.

Structure rules:
- Keep the intro short (2–3 sentences).
- Use a clear H2/H3 hierarchy.
- Write scannable paragraphs (3–4 sentences max).
- Use bullet lists and real markdown tables where they genuinely aid
  comprehension. If using a table, use valid markdown table syntax with a header
  row and separator row; never write flattened table-like text.
- Include an FAQ section when search intent is clearly informational.
- Do not include product cards or product CTAs unless products are specifically
  required by the keyword and product data is available.
- No aggressive affiliate CTAs.
- Include 1-3 light internal CTA boxes only when real internal link targets are
  provided in the input context. Never invent internal URLs.

Tone:
- Useful, direct, practical.
- Avoid generic filler ("In today's world…", "It's important to note…").
- Avoid over-explaining basics a reader already knows.
- Avoid fake-expert phrasing and AI-slop language.
"""

_MONEY_POST_RULES = """
## Post type: money_post

Source format: HTML

Generate a commercial buyer guide. This is NOT a regular blog post — the
primary goal is to help the reader choose a product quickly and confidently.

Required HTML structure:

<article class="money-post">

  <section class="money-hero">
    [H1]
    [SHORT_BUYER_FOCUSED_INTRO — max 100 words; orient the reader to the buying
     decision, not a generic product category intro]
    <div class="top-picks-grid">
      [TOP_PICK_CARDS — 2–3 product cards for the top picks]
    </div>
  </section>

  <section class="comparison-section">
    <div class="table-wrap">
      [COMMERCIAL_COMPARISON_TABLE — see table rules below]
    </div>
  </section>

  <section class="guide-toc-section">
    <nav class="hdl-toc" aria-label="In this guide">
      [COMPACT_TOC — 5 to 7 anchors for quick picks, comparison, best by use
       case, product reviews, how to choose, FAQ]
    </nav>
  </section>

  <section class="jump-links-section">
    <nav class="jump-links" aria-label="Quick article navigation">
      [SHORT_JUMP_LINKS — 4 to 5 anchors pointing to top picks, quick comparison,
       full reviews, buying guide, FAQ]
    </nav>
  </section>

  <section class="methodology-box">
    <h2>How we chose these products</h2>
    [METHODOLOGY — sources used, whether products were tested or only
     researched, how buyer complaints were weighted, how conflicting specs
     were handled. Never claim testing unless personally_tested=true.]
  </section>

  <section class="decision-box">
    <h2>Best dehumidifier by use case</h2>
    <div class="decision-grid">
      [BEST_BY_USE_CASE_MODULES — map concrete buyer situations to specific
       products. For broad category pages include budget, bedroom, bathroom,
       mould, laundry drying, large-room, compact/small-space and warm/cold
       climate splits where product data supports them.]
    </div>
  </section>

  <section class="education-section">
    [IMPORTANT_CONTEXT — background knowledge the buyer needs before choosing.
     Keep it practical; cut anything that doesn't affect the buying decision.]
  </section>

  <section class="product-reviews">
    [PRODUCT_REVIEW_BLOCKS — one block per product, using the structure below]
  </section>

  <section class="buyer-guide">
    <h2>How to choose</h2>
    [FEATURE_BY_FEATURE_BUYING_ADVICE]
  </section>

  <section class="mistakes-section">
    <h2>Common mistakes to avoid</h2>
    [COMMON_BUYING_MISTAKES — concrete, specific to this product category]
  </section>

  <section class="faq-section">
    <h2>Frequently asked questions</h2>
    [FAQ]
  </section>

  <section class="final-verdict">
    <h2>Final recommendation</h2>
    [RECOMMENDATION — declare a winner or a clear use-case split; do not hedge]
  </section>

</article>

Above-the-fold rules:
- Do not start with a long generic intro.
- The first 400 words must help the reader choose — not educate them about the
  product category in general.
- Place top-pick cards immediately after the short intro.
- Put the comparison table before the jump-links nav so the buying answer lands
  before the page turns into navigation.
- For broad category money pages, add a short quick-answer block or direct
  verdict before deeper education: there is usually no single best product for
  every Australian home, so split warm/humid compressor picks from cold/damp
  desiccant picks when the data supports it.
- Keep the jump-links nav compact and below the comparison table.

Product depth rules:
- If `article_job.commercial_page_scope` is `broad_category_money_page`, include
  all available researched product cards up to 10 and write at least
  `article_job.minimum_product_count` full product review blocks.
- Do not call a four-product shortlist a complete broad "best Australia" guide.
- If fewer than the required product cards are available, say the guide is a
  shortlist and do not overclaim category authority.

Top-pick card structure:
<div class="product-card featured">
  <span class="badge">BADGE (e.g. Best Overall / Best Value / Budget Pick)</span>
  <figure class="product-image-wrap">
    [IF product_image_url is available in product data:
      <img src="PRODUCT_IMAGE_URL" alt="PRODUCT NAME">
     ELSE:
      <p class="product-image-placeholder" aria-hidden="true">PRODUCT NAME</p>]
  </figure>
  <h3>PRODUCT NAME</h3>
  <p><strong>Best for:</strong> WHO IT SUITS IN ONE LINE</p>
  <ul>
    <li>KEY DECISION POINT 1</li>
    <li>KEY DECISION POINT 2</li>
    <li>KEY DECISION POINT 3 (optional)</li>
  </ul>
  <a class="button cta-button" href="#" data-product="PRODUCT_NAME">Check latest price</a>
  <a class="read-review-link" href="#PRODUCT-SLUG-review">Read review</a>
</div>

Comparison table rules:
- Use class="comparison-table" on the <table> element.
- Recommended columns: Model | Best for | Type | Key spec | Main caveat |
  Price range | CTA
- The CTA column must contain an anchor with class="table-cta":
  <a class="table-cta" href="#" data-product="PRODUCT_NAME">View</a>
- Use buyer-first columns, not spec-sheet columns.

Product review block structure:
<div class="product-review">
  <div class="product-header">
    <h2>RANK. PRODUCT NAME — <span class="badge">BEST-FOR BADGE</span></h2>
    <p class="verdict">ONE-LINE VERDICT</p>
  </div>
  <div class="product-layout">
    <div class="product-main">
      <h3>Why we picked it</h3>
      [CONTENT — review-led, based on buyer feedback patterns]
      <h3>Who should buy it</h3>
      [CONTENT]
      <h3>Who should avoid it</h3>
      [CONTENT]
      <div class="pros-cons">
        <ul class="pros">
          <li>PRO 1</li>
          <li>PRO 2</li>
        </ul>
        <ul class="cons">
          <li>CON 1</li>
          <li>CON 2</li>
        </ul>
      </div>
    </div>
    <div class="product-sidebar">
      <div class="spec-box">
        <h4>Key specs</h4>
        [SPECS — from product data only; do not invent]
      </div>
      <p><strong>Price range:</strong> PRICE RANGE or "Not confirmed"</p>
      <a class="button cta-button" href="#" data-product="PRODUCT_NAME">Check latest price</a>
    </div>
  </div>
</div>

Deep-review anchor rule:
- Every product-review block must have a stable id in the form `product-name-review`.
- The `Read review` link in each top-pick card must point to that matching id.

Decision module rules:
- Include at least 2 decision modules inside the decision-box section.
- Each module should answer a specific buyer question (e.g. "Which type suits
  your home?", "What capacity do you need?", "What should you avoid?").
- Keep each module concise and actionable.

Tone:
- Direct, buyer-focused, practical.
- Call out when a product is not suitable.
- Do not make every product sound equally good.
- Avoid hype, superlatives without evidence, and fake-testing claims.
"""

_SINGLE_PRODUCT_REVIEW_RULES = """
## Post type: single_product_review

Source format: HTML

Generate a dedicated one-product review. The reader wants to know: is this the
right product for me? Answer that quickly and clearly.

Required HTML structure:

<article class="single-product-review">

  <section class="review-hero">
    [H1]
    [SHORT_VERDICT — 2–3 sentences; give a clear recommendation up front]
    <div class="cta-box">
      <a class="button cta-button" href="#" data-product="PRODUCT_NAME">Check latest price</a>
    </div>
  </section>

  <section class="review-summary-box">
    <p><strong>Quick verdict:</strong> ONE SENTENCE SUMMARY</p>
    <p><strong>Best for:</strong> SPECIFIC USE CASE</p>
    <p><strong>Avoid if:</strong> CONDITION THAT MAKES IT A BAD CHOICE</p>
  </section>

  <section class="pros-cons-section">
    <div class="pros-cons">
      <ul class="pros">
        [PROS — specific, evidence-backed, not generic positives]
      </ul>
      <ul class="cons">
        [CONS — honest, specific; include real buyer complaints]
      </ul>
    </div>
  </section>

  <section class="specs-section">
    <h2>Key specifications</h2>
    <div class="spec-box">
      [KEY_SPECS_TABLE — from product data only; mark anything not confirmed]
    </div>
  </section>

  <section class="performance-section">
    <h2>Real-world performance</h2>
    [REAL_WORLD_USE_CASE_ANALYSIS — based on buyer feedback patterns and
     product specs; never claim hands-on testing unless personally_tested=true]
  </section>

  <section class="comparison-section">
    <h2>How it compares to alternatives</h2>
    [COMPARISON — name 1–2 alternatives and explain when to choose each.
     Use a small comparison table if 2+ alternatives are available.]
  </section>

  <section class="buyer-guide">
    <h2>Who should buy this</h2>
    [CONTENT]
    <h2>Who should look elsewhere</h2>
    [CONTENT — be direct; name a specific alternative if applicable]
  </section>

  <section class="faq-section">
    <h2>Frequently asked questions</h2>
    [FAQ]
  </section>

  <section class="final-verdict">
    <h2>Final verdict</h2>
    [RECOMMENDATION — clear, decisive; include a CTA button]
    <a class="button cta-button" href="#" data-product="PRODUCT_NAME">Check latest price</a>
  </section>

</article>

Rules:
- Never claim hands-on testing unless personally_tested=true for this product.
- Make the verdict clear within the first 300 words — do not bury it.
- Include CTA buttons near the top (in review-hero) and after the final verdict.
- Include pros and cons using real buyer feedback, not generic positives.
- Include a key specs table using data from the product record only.
- Mention limitations clearly; do not soften cons to the point of dishonesty.
"""

_PRODUCT_COMPARISON_RULES = """
## Post type: product_comparison

Source format: HTML

Generate a head-to-head product comparison. The reader has narrowed down to a
shortlist and wants to know which one to pick. Answer that quickly.

Required HTML structure:

<article class="product-comparison-post">

  <section class="comparison-hero">
    [H1]
    [SHORT_DECISION_LED_INTRO — 2–3 sentences; state the winner or the key
     decision split within the first 300 words]
    <div class="decision-box">
      <h2>Quick answer</h2>
      [WINNER STATEMENT — which product wins overall and why in 2–3 sentences.
       If it depends on use case, say so clearly and explain the split.]
    </div>
  </section>

  <section class="comparison-table-section">
    <h2>Head-to-head comparison</h2>
    <div class="table-wrap">
      [HEAD_TO_HEAD_TABLE — use class="comparison-table". Include a CTA column
       with class="table-cta" anchors.]
    </div>
  </section>

  <section class="winner-by-use-case">
    <h2>Which one wins for your situation?</h2>
    [USE_CASE_WINNER_TABLE_OR_LIST — for each key use case, declare a clear
     winner. Do not say "both are good" without a specific reason.]
  </section>

  <section class="product-breakdowns">
    [PRODUCT_BREAKDOWN_1 — detailed section for Product 1]
    [PRODUCT_BREAKDOWN_2 — detailed section for Product 2]
    [PRODUCT_BREAKDOWN_N — repeat for additional products if available]
  </section>

  <section class="decision-guide">
    <h2>How to choose between them</h2>
    [DECISION_FRAMEWORK — help the reader decide based on their situation.
     Use concrete criteria, not vague preferences.]
  </section>

  <section class="faq-section">
    <h2>Frequently asked questions</h2>
    [FAQ]
  </section>

  <section class="final-verdict">
    <h2>Final verdict</h2>
    [FINAL_WINNER — declare a winner with clear reasoning. Do not hedge.
     Include CTA buttons for each product.]
  </section>

</article>

Rules:
- The reader should know the overall winner (or use-case split) within the
  first 300 words. Do not bury the conclusion.
- Include a winner-by-use-case section so readers with different needs get a
  direct answer.
- Do not present every product as equally good — meaningful differences must be
  called out.
- Use a comparison table near the top.
- Include a CTA button (class="button cta-button") for each product in the
  final verdict.
- If one product is clearly better for most readers, say so directly.
"""

_BEST_X_FOR_Y_RULES = """
## Post type: best_x_for_y

Source format: HTML

Generate a use-case-driven money post. Every recommendation must be justified
by how well it fits the specific "for Y" use case — this is NOT a generic
best-products list.

Examples of this post type:
- Best dehumidifier for mould
- Best air purifier for dust mites
- Best mattress for back pain
- Best portable AC for small apartments

Required HTML structure:

<article class="best-x-for-y-post">

  <section class="money-hero">
    [H1]
    [PROBLEM_FOCUSED_INTRO — explain the specific problem/use-case (the "for Y"
     part) and why product selection matters for it. Max 120 words.]
    <div class="top-picks-grid">
      [TOP_PICK_CARDS — 2–3 product cards, each explicitly tied to the use case]
    </div>
  </section>

  <section class="comparison-section">
    <div class="table-wrap">
      [USE_CASE_COMPARISON_TABLE — columns must be tied to the specific use
       case, not just generic specs. Include a "Use-case fit" column.]
    </div>
  </section>

  <section class="jump-links-section">
    <nav class="jump-links" aria-label="Quick article navigation">
      [SHORT_JUMP_LINKS — 4 to 5 anchors pointing to top picks, quick comparison,
       use-case fit, full reviews, FAQ]
    </nav>
  </section>

  <section class="use-case-decision-box">
    <h2>Which one suits your situation?</h2>
    [FAST_USE_CASE_RECOMMENDATIONS — e.g. "For severe mould: [Product A].
     For mild dampness: [Product B]. For large rooms: [Product C]."
     Be specific; do not be vague.]
  </section>

  <section class="methodology-box">
    <h2>How we chose these products</h2>
    [METHODOLOGY — explain how use-case fit was weighted. Sources used.
     Whether products were tested or researched. Never claim testing unless
     personally_tested=true.]
  </section>

  <section class="problem-context-section">
    <h2>Why the right product matters for [USE CASE]</h2>
    [CONTEXT — explain the use case in enough detail that the reader
     understands why generic product choice would be a mistake.
     E.g. for mould: why humidity level and extraction rate matter.]
  </section>

  <section class="product-reviews">
    [PRODUCT_REVIEW_BLOCKS — one block per product. Each block must explain
     WHY this product suits the "for Y" use case specifically.]
  </section>

  <section class="buyer-guide">
    <h2>How to choose for [USE CASE]</h2>
    [BUYING_CRITERIA_SPECIFIC_TO_USE_CASE — not generic buying advice.
     Reference the specific requirements of the use case.]
  </section>

  <section class="mistakes-section">
    <h2>Common mistakes when buying for [USE CASE]</h2>
    [MISTAKES_SPECIFIC_TO_USE_CASE — not generic buying mistakes. Focus on
     errors people make specifically when buying for this use case.]
  </section>

  <section class="faq-section">
    <h2>Frequently asked questions</h2>
    [FAQ — questions specific to the "for Y" use case]
  </section>

  <section class="final-verdict">
    <h2>Final recommendation</h2>
    [RECOMMENDATION — tie the verdict back to the use case explicitly.]
  </section>

</article>

Top-pick card structure (same as money_post):
<div class="product-card featured">
  <span class="badge">BADGE</span>
  <figure class="product-image-wrap">
    [IF product_image_url is available in product data:
      <img src="PRODUCT_IMAGE_URL" alt="PRODUCT NAME">
     ELSE:
      <p class="product-image-placeholder" aria-hidden="true">PRODUCT NAME</p>]
  </figure>
  <h3>PRODUCT NAME</h3>
  <p><strong>Best for:</strong> SPECIFIC USE-CASE FIT</p>
  <ul>
    <li>WHY IT SUITS THE USE CASE — point 1</li>
    <li>WHY IT SUITS THE USE CASE — point 2</li>
  </ul>
  <a class="button cta-button" href="#" data-product="PRODUCT_NAME">Check latest price</a>
  <a class="read-review-link" href="#PRODUCT-SLUG-review">Read review</a>
</div>

Rules:
- The first screen must answer which product fits the specific "for Y" problem.
- Every product recommendation must explain how it addresses the use case —
  not just general strengths.
- Common mistakes and buying criteria must be use-case-specific.
- Do not recommend products just because they are popular or well-reviewed in
  general — justify them for this specific use case.
- Put the top-picks grid immediately after the intro, then the comparison table.
- Add the jump-links nav after the comparison table so commercial content leads.
- Include a use-case-decision-box near the top with fast, specific guidance.
- Match every top-pick `Read review` link to a deep-review block id in the form
  `product-name-review`.
"""

# ---------------------------------------------------------------------------
# Rules map and public API
# ---------------------------------------------------------------------------
_RULES_MAP: dict[str, str] = {
    "informational_blog": _INFORMATIONAL_BLOG_RULES + _RENDERING_RULES,
    "money_post": _MONEY_POST_RULES + _RENDERING_RULES,
    "single_product_review": _SINGLE_PRODUCT_REVIEW_RULES + _RENDERING_RULES,
    "product_comparison": _PRODUCT_COMPARISON_RULES + _RENDERING_RULES,
    "best_x_for_y": _BEST_X_FOR_Y_RULES + _RENDERING_RULES,
}


def get_post_type_generation_rules(post_type: str) -> str:
    """Return HTML structure and content generation rules for the given post type.

    Falls back to informational_blog rules for unrecognised post types.
    """
    rules = _RULES_MAP.get(post_type)
    if rules is None:
        logger.warning(
            "Unknown post_type %r — falling back to informational_blog generation rules.",
            post_type,
        )
        return _RULES_MAP["informational_blog"]
    logger.info("Using post type generation rules: %s", post_type)
    return rules
