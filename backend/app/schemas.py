from typing import Any

from pydantic import BaseModel, Field

from .ai import SuggestedUpdate


class CaptureRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    confirm: bool = True


class CreateObjectRequest(BaseModel):
    attributes: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class MeetingPrepRequest(BaseModel):
    meeting: str = Field(default="", max_length=500)


class CaptureClassificationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    confirm: bool = False


class CaptureConfirmationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    approved_updates: list[SuggestedUpdate] = Field(default_factory=list, max_length=50)
