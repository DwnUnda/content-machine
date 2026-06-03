from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app


def test_article_creation_writes_local_export_bundle(monkeypatch, tmp_path):
    export_root = tmp_path / "Completed-Articles"
    monkeypatch.setattr("app.core.config.COMPLETED_ARTICLES_DIR", export_root)
    monkeypatch.setattr("app.services.local_exports.COMPLETED_ARTICLES_DIR", export_root)

    client = TestClient(app)
    created = client.post(
        "/api/article-jobs",
        json={
            "title": "Humidity and mould in Australian homes",
            "primary_keyword": "What humidity level causes mould in Australian homes?",
            "post_type": "informational_blog",
        },
    ).json()

    detail = client.get(f"/api/article-jobs/{created['id']}").json()
    export_path = Path(detail["local_export_path"])

    assert export_path.exists()
    assert (export_path / "article.json").exists()
    assert export_path.parent.name == "articles"
