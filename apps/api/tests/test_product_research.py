from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import ArticleJobProduct, Product
from app.services.product_research import NOT_CONFIRMED, calculate_confidence, clean_product_url, extract_product_data_from_html


HTML_SAMPLE = """
<html>
  <head>
    <title>AusClimate NWT Medium 20L Dehumidifier</title>
    <meta name="description" content="20L dehumidifier with continuous drainage and 2 year warranty." />
  </head>
  <body>
    <h1>AusClimate NWT Medium 20L Dehumidifier</h1>
    <table>
      <tr><th>Capacity</th><td>20L/day</td></tr>
      <tr><th>Tank Size</th><td>4L</td></tr>
      <tr><th>Noise Level</th><td>42dB</td></tr>
      <tr><th>Power Input</th><td>420W</td></tr>
      <tr><th>Warranty</th><td>2 years</td></tr>
      <tr><th>Manufacturer's Part Number</th><td>DDSX220WF</td></tr>
    </table>
    <p>Price: $399. Continuous drainage supported. Good for 40m2 rooms.</p>
  </body>
</html>
"""


HTML_MISSING = """
<html>
  <head><title>Basic Product Page</title></head>
  <body><h1>Basic Product Page</h1><p>Minimal information only.</p></body>
</html>
"""

def test_extract_product_data_from_html():
    data = extract_product_data_from_html("https://example.com.au/product", HTML_SAMPLE, source_type="retailer")
    assert data["name"] == "AusClimate NWT Medium 20L Dehumidifier"
    assert data["brand"] == "AusClimate"
    assert data["model_number"] == "DDSX220WF"
    assert data["capacity_text"] == "20L/day"
    assert data["tank_size_text"] == "4L"
    assert data["power_use_text"] == "420W"
    assert data["confidence_level"] in {"Medium", "High"}


def test_missing_specs_become_not_confirmed():
    data = extract_product_data_from_html("https://example.com/basic", HTML_MISSING, source_type="other")
    assert data["price_text"] == NOT_CONFIRMED
    assert data["capacity_text"] == NOT_CONFIRMED
    assert data["warranty_text"] == NOT_CONFIRMED


def test_confidence_scoring():
    assert calculate_confidence(source_types={"manufacturer", "retailer"}, key_spec_count=4) == ("High", 90)
    assert calculate_confidence(source_types={"retailer"}, key_spec_count=2) == ("Medium", 65)
    assert calculate_confidence(source_types={"other"}, key_spec_count=0) == ("Low", 30)


def test_failed_extraction_handled(monkeypatch):
    client = TestClient(app)
    article = client.post(
        "/api/article-jobs",
        json={"title": "Product Test", "primary_keyword": "best dehumidifier", "post_type": "money_post"},
    ).json()
    source = client.post(
        f"/api/article-jobs/{article['id']}/product-sources",
        json={"source_url": "https://example.com/product", "source_type": "retailer"},
    ).json()

    def fail_fetch(url: str):  # noqa: ARG001
        raise RuntimeError("blocked page")

    monkeypatch.setattr("app.services.product_research._fetch_html_http", fail_fetch)
    monkeypatch.setattr("app.services.product_research._fetch_html_playwright", fail_fetch)
    response = client.post(f"/api/article-jobs/{article['id']}/extract-product", json={"product_source_id": source["id"]})
    assert response.status_code == 200
    assert response.json()["extraction_status"] == "extraction_failed"


def test_product_linked_to_article(monkeypatch):
    client = TestClient(app)
    article = client.post(
        "/api/article-jobs",
        json={"title": "Product Link Test", "primary_keyword": "best dehumidifier", "post_type": "money_post"},
    ).json()
    source = client.post(
        f"/api/article-jobs/{article['id']}/product-sources",
        json={"source_url": "https://example.com.au/product", "source_type": "retailer"},
    ).json()

    monkeypatch.setattr("app.services.product_research._fetch_html_http", lambda url: HTML_SAMPLE)

    response = client.post(f"/api/article-jobs/{article['id']}/extract-product", json={"product_source_id": source["id"]})
    assert response.status_code == 200
    assert response.json()["product"]["name"] == "AusClimate NWT Medium 20L Dehumidifier"

    db = SessionLocal()
    try:
        assert db.query(ArticleJobProduct).filter(ArticleJobProduct.article_job_id == article["id"]).count() == 1
        assert db.query(Product).count() == 1
    finally:
        db.close()


def test_clean_product_url_removes_tracking_params():
    cleaned = clean_product_url("https://example.com.au/product?utm_source=test&gclid=123&id=42#section")
    assert cleaned == "https://example.com.au/product?id=42"


def test_product_readiness_missing_fields_are_exposed(monkeypatch):
    client = TestClient(app)
    article = client.post(
        "/api/article-jobs",
        json={"title": "Product Readiness", "primary_keyword": "best dehumidifier", "post_type": "money_post"},
    ).json()
    source = client.post(
        f"/api/article-jobs/{article['id']}/product-sources",
        json={"source_url": "https://example.com.au/product?utm_source=test", "source_type": "retailer"},
    ).json()

    monkeypatch.setattr("app.services.product_research._fetch_html_http", lambda url: HTML_MISSING)

    extract_response = client.post(f"/api/article-jobs/{article['id']}/extract-product", json={"product_source_id": source["id"]})
    assert extract_response.status_code == 200

    products_response = client.get(f"/api/article-jobs/{article['id']}/products")
    assert products_response.status_code == 200
    row = products_response.json()["items"][0]
    assert row["draft_ready"] is False
    assert row["readiness_status"] == "Needs manual edit"
    assert "missing best for" in row["missing_fields"]
    assert row["cleaned_source_url"] == "https://example.com.au/product"


def test_product_draft_ready_does_not_require_buyer_notes():
    client = TestClient(app)
    article = client.post(
        "/api/article-jobs",
        json={"title": "Draft Ready Product", "primary_keyword": "best dehumidifier", "post_type": "money_post"},
    ).json()

    db = SessionLocal()
    try:
        product = Product(
            name="AusClimate NWT Medium 20L Dehumidifier",
            brand="AusClimate",
            best_for="Australian homes dealing with mould-prone rooms",
            common_complaints="Water tank is a bit small for heavy use.",
            extraction_status="completed",
        )
        db.add(product)
        db.flush()
        db.add(
            ArticleJobProduct(
                article_job_id=article["id"],
                product_id=product.id,
                source_url="https://example.com.au/product",
                original_source_url="https://example.com.au/product",
                cleaned_source_url="https://example.com.au/product",
                source_type="retailer",
                extraction_status="completed",
            )
        )
        db.commit()
        row = db.query(ArticleJobProduct).filter(ArticleJobProduct.article_job_id == article["id"]).one()
        assert row.draft_ready is True
        assert row.readiness_status == "Draft ready"
        assert "missing who should buy" in row.missing_fields
        assert "missing who should avoid" in row.missing_fields
    finally:
        db.close()
