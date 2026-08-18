from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RubricSource, RubricStatus


class RubricItemBase(BaseModel):
    criterion: str
    description: str
    max_score: Decimal = Field(max_digits=10, decimal_places=2)
    evaluation_guide: dict[str, Any] = Field(default_factory=dict)
    expected_evidence: list[Any] = Field(default_factory=list)


class RubricItemCreate(RubricItemBase):
    pass


class RubricCreate(BaseModel):
    items: list[RubricItemCreate]


class RubricUpdate(BaseModel):
    items: list[RubricItemCreate]


class RubricItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    criterion: str
    description: str
    max_score: Decimal
    evaluation_guide: dict[str, Any]
    expected_evidence: list[Any]
    sort_order: int
    created_at: datetime


class RubricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    assignment_id: int
    version: int
    source: RubricSource
    status: RubricStatus
    locked_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[RubricItemRead]


class RubricValidationIssue(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class RubricValidationResponse(BaseModel):
    valid: bool
    errors: list[RubricValidationIssue]
