from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.html_validation import validate_html_structure


VALID_BEST_X_HTML = """
<!-- wp:html -->
<style>.hdl-article-content { color: #111; }</style>
<div class="hdl-article-content">
<article class="best-x-for-y-post">
  <section class="money-hero">
    <h1>Best dehumidifier for mould</h1>
    <div class="top-picks-grid">
      <div class="product-card featured"><h3>Pick One</h3><a class="read-review-link" href="#pick-one-review">Read review</a></div>
      <div class="product-card featured"><h3>Pick Two</h3><a class="read-review-link" href="#pick-two-review">Read review</a></div>
      <div class="product-card featured"><h3>Pick Three</h3><a class="read-review-link" href="#pick-three-review">Read review</a></div>
    </div>
  </section>
  <section class="hdl-comparison-module">
    <h2>Quick comparison</h2>
    <div class="hdl-table-wrap">
      <table class="hdl-table"><thead><tr><th>Model</th></tr></thead><tbody><tr><td>Pick One</td></tr></tbody></table>
    </div>
  </section>
  <section class="hdl-product-reviews">
    <article class="hdl-product-review-card" id="pick-one-review"><h3>Pick One</h3></article>
    <article class="hdl-product-review-card" id="pick-two-review"><h3>Pick Two</h3></article>
    <article class="hdl-product-review-card" id="pick-three-review"><h3>Pick Three</h3></article>
  </section>
  <section class="hdl-faq-section"><h2>Frequently asked questions</h2><div class="hdl-faq-accordion"><details><summary>Question?</summary><p>Answer.</p></details></div></section>
</article>
</div>
<!-- /wp:html -->
"""


def test_valid_commercial_html_passes():
    result = validate_html_structure(VALID_BEST_X_HTML, post_type="best_x_for_y", expect_wordpress_block=True)

    assert result.passed is True
    assert result.summary == "HTML structure passed."


def test_validation_catches_raw_markdown_and_missing_wordpress_block():
    result = validate_html_structure(
        '<div class="hdl-article-content">\n## Raw heading\n<p>Body</p>\n</div>',
        post_type="informational_blog",
        expect_wordpress_block=True,
    )

    failed = {check.key for check in result.checks if not check.passed}
    assert "no_raw_markdown" in failed
    assert "wordpress_block" in failed


def test_validation_catches_missing_comparison_rows():
    html = VALID_BEST_X_HTML.replace("<tbody><tr><td>Pick One</td></tr></tbody>", "<tbody></tbody>")

    result = validate_html_structure(html, post_type="best_x_for_y", expect_wordpress_block=True)

    failed = {check.key for check in result.checks if not check.passed}
    assert "comparison_table" in failed


def test_validation_catches_broken_read_review_anchor():
    html = VALID_BEST_X_HTML.replace('id="pick-three-review"', 'id="different-review"')

    result = validate_html_structure(html, post_type="best_x_for_y", expect_wordpress_block=True)

    failed = {check.key for check in result.checks if not check.passed}
    assert "review_anchor_targets" in failed
