from pydantic import BaseModel


class ContentRuleItem(BaseModel):
    key: str
    label: str
    description: str
    category: str
    value: str


class ContentRulesResponse(BaseModel):
    items: list[ContentRuleItem]


class ContentRuleUpdate(BaseModel):
    value: str


class ManualReviewOverrideRequest(BaseModel):
    enabled: bool = True

