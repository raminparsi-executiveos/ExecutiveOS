from typing import Any

from pydantic import BaseModel, Field, model_validator

from .ai import SuggestedUpdate


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


class MeetingPrepRequest(BaseModel):
    meeting: str = Field(default="", max_length=500)


class CaptureClassificationRequest(BaseModel):
    text: str = Field(default="", max_length=20_000)
    image_data: str = Field(
        default="",
        max_length=7_000_000,
        pattern=r"^(?:|data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+)$",
    )
    confirm: bool = False

    @model_validator(mode="after")
    def require_capture_input(self):
        if not self.text.strip() and not self.image_data:
            raise ValueError("Enter text or attach a screenshot")
        return self


class CaptureConfirmationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    approved_updates: list[SuggestedUpdate] = Field(default_factory=list, max_length=50)
    classification_source: str = Field(default="unknown", max_length=50)
