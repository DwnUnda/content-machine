from pydantic import BaseModel, Field


class ArticleRecoveryRequest(BaseModel):
    bundle_path: str = Field(min_length=1)
