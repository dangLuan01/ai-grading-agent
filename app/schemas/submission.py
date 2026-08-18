from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SubmissionFileParseStatus, SubmissionStatus
from app.schemas.student import StudentRead


class SubmissionImportRowInput(BaseModel):
    student_code: str | None = None
    student_name: str | None = None
    repository_url: str | None = None


class SubmissionImportJsonRequest(BaseModel):
    submissions: list[SubmissionImportRowInput] = Field(min_length=1)


ImportRowStatus = Literal[
    "VALID",
    "INVALID",
    "IMPORTED",
    "INVENTORIED",
    "FAILED",
]


class SubmissionImportRowResult(BaseModel):
    row: int
    student_code: str | None = None
    student_name: str | None = None
    repository_url: str | None = None
    status: ImportRowStatus
    errors: list[str] = Field(default_factory=list)
    submission_id: int | None = None


class SubmissionImportResponse(BaseModel):
    total: int
    valid: int
    invalid: int
    imported: int
    failed: int
    dry_run: bool
    rows: list[SubmissionImportRowResult]


class SubmissionFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    path: str
    blob_sha: str | None
    extension: str | None
    content_type: str | None
    size_bytes: int
    parse_status: SubmissionFileParseStatus
    parse_error: str | None
    created_at: datetime


class SubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    assignment_id: int
    student_id: int
    student: StudentRead
    repository_url: str
    repository_owner: str | None
    repository_name: str | None
    branch: str | None
    commit_sha: str | None
    rubric_id: int | None
    rubric_version_used: int | None
    status: SubmissionStatus
    submitted_at: datetime
    created_at: datetime
    files: list[SubmissionFileRead] = Field(default_factory=list)
