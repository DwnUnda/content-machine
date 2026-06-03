from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.content_rules import ContentRuleItem, ContentRulesResponse, ContentRuleUpdate
from app.services.content_rules import CONTENT_RULE_METADATA, list_content_rules, update_content_rule


router = APIRouter()


@router.get("/settings/content-rules", response_model=ContentRulesResponse)
def get_content_rules(db: Session = Depends(get_db)) -> ContentRulesResponse:
    items = list_content_rules(db)
    return ContentRulesResponse(
        items=[
            ContentRuleItem(
                key=item.key,
                label=CONTENT_RULE_METADATA.get(item.key, {}).get("label", item.key),
                description=CONTENT_RULE_METADATA.get(item.key, {}).get("description", item.description or ""),
                category=item.category or "content_rules",
                value=item.value or "",
            )
            for item in items
        ]
    )


@router.put("/settings/content-rules/{rule_key:path}", response_model=ContentRuleItem)
def put_content_rule(rule_key: str, payload: ContentRuleUpdate, db: Session = Depends(get_db)) -> ContentRuleItem:
    setting = update_content_rule(db, rule_key, payload.value)
    if not setting:
        raise HTTPException(status_code=404, detail="Content rule not found")
    return ContentRuleItem(
        key=setting.key,
        label=CONTENT_RULE_METADATA.get(setting.key, {}).get("label", setting.key),
        description=CONTENT_RULE_METADATA.get(setting.key, {}).get("description", setting.description or ""),
        category=setting.category or "content_rules",
        value=setting.value or "",
    )
