from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.post_type_generation_rules import get_post_type_generation_rules


def test_money_post_contains_article_class():
    rules = get_post_type_generation_rules("money_post")
    assert '<article class="money-post">' in rules


def test_best_x_for_y_contains_article_class():
    rules = get_post_type_generation_rules("best_x_for_y")
    assert '<article class="best-x-for-y-post">' in rules


def test_informational_blog_contains_article_class():
    rules = get_post_type_generation_rules("informational_blog")
    assert '<article class="informational-post">' in rules
    assert "Source format: Markdown" in rules


def test_informational_blog_rules_include_support_article_guardrails():
    rules = get_post_type_generation_rules("informational_blog")
    assert "support article" in rules
    assert "1,200-2,000 words" in rules
    assert "4-6 questions max" in rules
    assert "[[RELATEDBUYINGGUIDE|" in rules


def test_single_product_review_contains_article_class():
    rules = get_post_type_generation_rules("single_product_review")
    assert '<article class="single-product-review">' in rules


def test_product_comparison_contains_article_class():
    rules = get_post_type_generation_rules("product_comparison")
    assert '<article class="product-comparison-post">' in rules


def test_unknown_post_type_falls_back_to_informational_blog():
    rules = get_post_type_generation_rules("unknown_type")
    assert '<article class="informational-post">' in rules


def test_all_post_types_include_html_quality_rules():
    post_types = [
        "informational_blog",
        "money_post",
        "single_product_review",
        "product_comparison",
        "best_x_for_y",
    ]
    for pt in post_types:
        rules = get_post_type_generation_rules(pt)
        assert "Rendered HTML rules" in rules, f"{pt} missing rendered HTML rules"
        assert "cta-button" in rules, f"{pt} missing cta-button class reference"


def test_commercial_post_types_remain_html_first():
    for pt in [
        "money_post",
        "single_product_review",
        "product_comparison",
        "best_x_for_y",
    ]:
        rules = get_post_type_generation_rules(pt)
        assert "Source format: HTML" in rules


def test_money_post_rules_include_required_sections():
    rules = get_post_type_generation_rules("money_post")
    assert "money-hero" in rules
    assert "methodology-box" in rules
    assert "decision-box" in rules
    assert "product-reviews" in rules
    assert "final-verdict" in rules


def test_best_x_for_y_rules_include_use_case_decision_box():
    rules = get_post_type_generation_rules("best_x_for_y")
    assert "use-case-decision-box" in rules


def test_rules_are_non_empty_strings():
    post_types = [
        "informational_blog",
        "money_post",
        "single_product_review",
        "product_comparison",
        "best_x_for_y",
    ]
    for pt in post_types:
        rules = get_post_type_generation_rules(pt)
        assert isinstance(rules, str)
        assert len(rules) > 500, f"{pt} rules suspiciously short"
