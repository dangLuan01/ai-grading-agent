from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class AssignmentAnalysisOutput(BaseModel):
    assignment_type: str = Field(min_length=1)
    requirements: list[str] = Field(min_length=1)
    expected_outputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class AIRubricItemOutput(BaseModel):
    criterion: str = Field(min_length=1)
    description: str = Field(min_length=1)
    max_score: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    evaluation_guide: dict[str, Any] = Field(default_factory=dict)
    expected_evidence: list[str] = Field(default_factory=list)


class AIRubricGenerationOutput(BaseModel):
    assignment_type: str = Field(min_length=1)
    requirements: list[str] = Field(min_length=1)
    rubric: list[AIRubricItemOutput] = Field(min_length=1)


class AIRubricValidationWarning(BaseModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    criterion: str | None = None


class AIRubricValidationOutput(BaseModel):
    valid: bool
    warnings: list[AIRubricValidationWarning] = Field(default_factory=list)
