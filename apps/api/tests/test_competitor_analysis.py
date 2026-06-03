from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import CompetitorAnalysisReport, CompetitorPage, SerpResult
from app.services.competitor_extraction import classify_page_type, extract_page_data_from_html, score_australian_relevance


HTML_SAMPLE = """
<html>
  <head>
    <title>Best Dehumidifier for Mould in Australia</title>
    <meta name="description" content="Australian guide to choosing a dehumidifier for mould." />
  </head>
  <body>
    <h1>Best Dehumidifier for Mould in Australia</h1>
    <h2>How we chose the best models</h2>
    <h2>FAQ</h2>
    <h3>What size room does it suit?</h3>
    <h3>Is it rental friendly?</h3>
    <table><tr><td>Model</td></tr></table>
    <p>In Australia, mould is common in Brisbane rentals and coastal homes.</p>
    <p>Harvey Norman and The Good Guys both list popular AusClimate and Breville units.</p>
  </body>
</html>
"""
def test_classify_page_type():
    assert classify_page_type("https://www.harveynorman.com.au/dehumidifiers", "Dehumidifiers", "Add to cart $299") == "retailer"
    assert classify_page_type("https://www.health.gov.au/article", "Mould advice", "Australian health advice") == "government/health source"
    assert classify_page_type("https://example.com/best-dehumidifier-review", "Best dehumidifier review", "We may earn affiliate commission") == "affiliate/review site"


def test_score_australian_relevance():
    score, signals = score_australian_relevance(
        "https://www.example.com.au/product",
        "Australian mould guide for Brisbane rentals with AUD pricing and laundry advice.",
    )
    assert score >= 50
    assert any("Australia/Australian" in signal for signal in signals)


def test_extract_page_data_from_html():
    data = extract_page_data_from_html("https://www.example.com.au/best", HTML_SAMPLE, extraction_method="http")
    assert data["title"] == "Best Dehumidifier for Mould in Australia"
    assert data["h1"] == "Best Dehumidifier for Mould in Australia"
    assert len(data["h2_list"]) == 2
    assert len(data["h3_list"]) == 2
    assert "What size room does it suit?" in data["faq_headings"]
    assert data["tables_count"] == 1
    assert data["australian_relevance_score"] > 0


def test_extract_competitors_failure_handled(monkeypatch):
    client = TestClient(app)
    article = client.post(
        "/api/article-jobs",
        json={"title": "Competitor Test", "primary_keyword": "best mould dehumidifier", "post_type": "money_post"},
    ).json()
    db = SessionLocal()
    try:
        db.add(
            SerpResult(
                article_job_id=article["id"],
                keyword="best mould dehumidifier",
                position=1,
                title="Example competitor",
                url="https://example.com/best",
                domain="example.com",
                result_type="organic",
            )
        )
        db.commit()
    finally:
        db.close()

    def fail_fetch(url: str):
        raise RuntimeError("blocked page")

    monkeypatch.setattr("app.services.competitor_extraction._fetch_html_http", fail_fetch)
    monkeypatch.setattr("app.services.competitor_extraction._fetch_html_playwright", fail_fetch)
    response = client.post(f"/api/article-jobs/{article['id']}/extract-competitors")
    assert response.status_code == 200

    db = SessionLocal()
    try:
        rows = db.query(CompetitorPage).filter(CompetitorPage.article_job_id == article["id"]).all()
        assert rows
        assert any(row.extraction_status == "failed" for row in rows)
    finally:
        db.close()


def test_serp_analysis_report_with_mocked_competitors():
    client = TestClient(app)
    article = client.post(
        "/api/article-jobs",
        json={"title": "Analysis Test", "primary_keyword": "best dehumidifier australia", "post_type": "money_post"},
    ).json()

    db = SessionLocal()
    try:
        db.add(
            CompetitorPage(
                article_job_id=article["id"],
                title="Best Dehumidifier for Mould",
                url="https://www.example.com.au/best",
                domain="www.example.com.au",
                page_type="affiliate/review site",
                h2_list=["How we chose", "Running costs"],
                h3_list=["What room size suits?", "Is it rental friendly?"],
                faq_headings=["What room size suits?"],
                detected_product_names=["AusClimate NWT Medium"],
                australian_relevance_score=70,
                visible_text_extract="Australian mould guide with running cost notes.",
                extraction_status="success",
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.post(f"/api/article-jobs/{article['id']}/analyse-serp")
    assert response.status_code == 200

    db = SessionLocal()
    try:
        report = db.query(CompetitorAnalysisReport).filter(CompetitorAnalysisReport.article_job_id == article["id"]).first()
        assert report is not None
        assert report.dominant_intent in {"commercial investigation", "informational", "mixed"}
        assert report.original_value_recommendations_json
    finally:
        db.close()
