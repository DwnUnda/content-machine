from pydantic import BaseModel


class SettingPresence(BaseModel):
    key: str
    present: bool


class SettingsValidationResponse(BaseModel):
    site_name: str
    site_url_present: bool
    target_country: str
    target_language: str
    required: list[SettingPresence]

