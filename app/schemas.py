from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator


class JobCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    event_name: str = Field(min_length=1, max_length=200)
    issuer: str = Field(min_length=1, max_length=200)
    recipients: list[Any] = Field(min_length=1, max_length=1000)


class RecipientInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("name must not be blank")
        return value


recipient_adapter = TypeAdapter(RecipientInput)