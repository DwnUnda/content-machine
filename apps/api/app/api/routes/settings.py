from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.settings import SettingPresence, SettingsValidationResponse


router = APIRouter()


@router.get("/settings/validation", response_model=SettingsValidationResponse)
def validate_settings() -> SettingsValidationResponse:
    settings = get_settings()
    required_fields = [
        ("DATAFORSEO_LOGIN", settings.dataforseo_login),
        ("DATAFORSEO_PASSWORD", settings.dataforseo_password),
        ("ANTHROPIC_API_KEY", settings.anthropic_api_key),
        ("ANTHROPIC_MODEL", settings.anthropic_model),
        ("OPENAI_API_KEY", settings.openai_api_key),
        ("OPENAI_MODEL", settings.openai_model),
        ("WORDPRESS_BASE_URL", settings.wordpress_base_url),
        ("WORDPRESS_USERNAME", settings.wordpress_username),
        ("WORDPRESS_APP_PASSWORD", settings.wordpress_app_password),
    ]
    return SettingsValidationResponse(
        site_name=settings.site_name,
        site_url_present=bool(settings.site_url),
        target_country=settings.target_country,
        target_language=settings.target_language,
        required=[SettingPresence(key=key, present=bool(value)) for key, value in required_fields],
    )
