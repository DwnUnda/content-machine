from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "app.db"
COMPLETED_ARTICLES_DIR = ROOT_DIR / "Completed-Articles"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Home Dry Lab Content Machine"
    environment: str = "development"
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    dataforseo_login: str | None = None
    dataforseo_password: str | None = None
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    openai_image_model: str | None = None
    wordpress_base_url: str | None = None
    wordpress_username: str | None = None
    wordpress_app_password: str | None = None
    visuals_enabled: bool = True
    visuals_output_format: str = "webp"
    anthropic_visual_model: str | None = None
    site_name: str = "Home Dry Lab"
    site_url: str | None = None
    target_country: str = "Australia"
    target_language: str = "en-AU"


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    COMPLETED_ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
