from typing import Any

from pydantic import BaseModel, Field


class CaptureRequest(BaseModel):
    text: str
    confirm: bool = True


class CreateObjectRequest(BaseModel):
    attributes: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str


class MeetingPrepRequest(BaseModel):
    meeting: str = ""


class CaptureClassificationRequest(BaseModel):
    text: str
    confirm: bool = False


class CaptureConfirmationRequest(BaseModel):
    text: str
    approved_updates: list[dict[str, Any]] = Field(default_factory=list)
