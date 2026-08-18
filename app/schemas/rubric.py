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
    model_config = ConfigDict(extra="forbid")


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


class RubricValidationWarning(BaseModel):
    code: str
    message: str
    criterion: str | None = None


class RubricValidationResponse(BaseModel):
    valid: bool
    ai_valid: bool | None = None
    errors: list[RubricValidationIssue]
    warnings: list[RubricValidationWarning] = Field(default_factory=list)
    ai_prompt_version: str | None = None


class AssignmentAnalysisRead(BaseModel):
    assignment_type: str
    requirements: list[str]
    expected_outputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class RubricGenerateResponse(BaseModel):
    rubric: RubricRead
    analysis: AssignmentAnalysisRead
    ai_valid: bool
    warnings: list[RubricValidationWarning] = Field(default_factory=list)
    prompt_versions: dict[str, str]
