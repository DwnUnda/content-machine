from pydantic import BaseModel

from app.schemas.common import TimestampedResponse


class WorkflowRunStepResponse(TimestampedResponse):
    workflow_run_id: int
    step_key: str
    step_label: str
    status: str
    message: str | None = None


class WorkflowRunResponse(TimestampedResponse):
    article_job_id: int
    workflow_mode: str
    research_mode: str
    status: str
    current_step: str | None = None
    summary_message: str | None = None
    steps: list[WorkflowRunStepResponse] = []


class FullWorkflowRequest(BaseModel):
    research_mode: str = "fresh"


class WorkflowStateStepResponse(BaseModel):
    step_key: str
    step_label: str
    status: str
    detail: str | None = None
    paid_step: bool = False


class PublishReadinessCheckResponse(BaseModel):
    key: str
    label: str
    passed: bool
    detail: str | None = None


class PublishReadinessResponse(BaseModel):
    ready: bool
    summary: str
    checks: list[PublishReadinessCheckResponse]
    html_validation: dict | None = None


class WorkflowStateResponse(BaseModel):
    article_job_id: int
    recommended_research_mode: str
    next_recommended_action: str
    next_step_key: str | None = None
    summary_message: str
    estimated_paid_calls: int
    has_existing_work: bool
    steps: list[WorkflowStateStepResponse]
    publish_readiness: PublishReadinessResponse | None = None
