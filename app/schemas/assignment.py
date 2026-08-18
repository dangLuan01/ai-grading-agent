from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AssignmentStatus


class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    total_score: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class AssignmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    total_score: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    status: AssignmentStatus | None = None


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    total_score: Decimal
    status: AssignmentStatus
    created_by: int
    created_at: datetime
    updated_at: datetime
