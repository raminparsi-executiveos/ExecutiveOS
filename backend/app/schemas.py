from typing import Annotated, Any

from pydantic import BaseModel, Field, model_validator

from .ai import SuggestedUpdate


ImageData = Annotated[
    str,
    Field(
        max_length=7_000_000,
        pattern=r"^data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+$",
    ),
]


class CaptureRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    confirm: bool = True


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=500)


class CreateObjectRequest(BaseModel):
    attributes: dict[str, Any] = Field(default_factory=dict)


class UpdateObjectRequest(BaseModel):
    attributes: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    company: str = Field(default="", max_length=100)
    record_types: list[str] = Field(default_factory=list, max_length=20)
    status: str = Field(default="", max_length=50)
    owner: str = Field(default="", max_length=100)
    priority: str = Field(default="", max_length=50)
    date_from: str = Field(default="", max_length=20)
    date_to: str = Field(default="", max_length=20)
    conversation_id: str = Field(default="", max_length=100)


class MeetingPrepRequest(BaseModel):
    meeting: str = Field(default="", max_length=500)
    meeting_type: str = Field(default="", max_length=100)
    excluded_sections: list[str] = Field(default_factory=list, max_length=20)


class CaptureClassificationRequest(BaseModel):
    text: str = Field(default="", max_length=20_000)
    image_data: str = Field(
        default="",
        max_length=7_000_000,
        pattern=r"^(?:|data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+)$",
    )
    image_data_list: list[ImageData] = Field(default_factory=list, max_length=5)
    confirm: bool = False

    @model_validator(mode="after")
    def require_capture_input(self):
        if not self.text.strip() and not self.image_inputs():
            raise ValueError("Enter text or attach a screenshot")
        return self

    def image_inputs(self) -> list[str]:
        images = list(self.image_data_list)
        if self.image_data:
            images.insert(0, self.image_data)
        return list(dict.fromkeys(images))


class CaptureConfirmationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    approved_updates: list[SuggestedUpdate] = Field(default_factory=list, max_length=50)
    classification_source: str = Field(default="unknown", max_length=50)


class ReviewAlertResolutionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=50)
    resolution: str = Field(default="", max_length=2_000)


class DashboardConfigRequest(BaseModel):
    modules: list[dict[str, Any]] = Field(default_factory=list, max_length=50)


class IntegrationInboxCreateRequest(BaseModel):
    source_type: str = Field(min_length=1, max_length=50)
    source_identifier: str = Field(default="", max_length=300)
    source_title: str = Field(default="", max_length=300)
    source_date: str = Field(default="", max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)
    extracted_text: str = Field(default="", max_length=100_000)


class IntegrationInboxDecisionRequest(BaseModel):
    suggestion_indexes: list[int] = Field(default_factory=list, max_length=50)
    status: str = Field(default="approved", max_length=50)


class EntityAliasRequest(BaseModel):
    entity_type: str = Field(min_length=1, max_length=50)
    entity_id: int = Field(ge=1)
    alias: str = Field(min_length=1, max_length=200)
    confidence: str = Field(default="user_confirmed", max_length=50)


class ClarificationAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=2_000)
    note: str = Field(default="", max_length=2_000)


class ClarificationConfirmRequest(BaseModel):
    update_indexes: list[int] = Field(default_factory=list, max_length=20)


class ClarificationSnoozeRequest(BaseModel):
    snoozed_until: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=2_000)


class ClarificationCloseRequest(BaseModel):
    reason: str = Field(default="", max_length=2_000)
    scope: str = Field(default="", max_length=300)


class LeadershipReviewGenerateRequest(BaseModel):
    review_type: str = Field(default="manual", max_length=20)
    company: str = Field(default="", max_length=100)
    force: bool = False


class LeadershipReviewProposalRequest(BaseModel):
    finding_indexes: list[int] = Field(default_factory=list, max_length=20)


class BackupImportRequest(BaseModel):
    backup: dict[str, Any] = Field(default_factory=dict)
    mode: str = Field(default="merge", max_length=20)
