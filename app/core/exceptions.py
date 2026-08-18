from enum import StrEnum
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ErrorCode(StrEnum):
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    INACTIVE_USER = "INACTIVE_USER"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    ASSIGNMENT_NOT_FOUND = "ASSIGNMENT_NOT_FOUND"
    ASSIGNMENT_ARCHIVED = "ASSIGNMENT_ARCHIVED"
    RUBRIC_NOT_FOUND = "RUBRIC_NOT_FOUND"
    RUBRIC_DRAFT_EXISTS = "RUBRIC_DRAFT_EXISTS"
    RUBRIC_LOCKED = "RUBRIC_LOCKED"
    RUBRIC_NOT_DRAFT = "RUBRIC_NOT_DRAFT"
    INVALID_GITHUB_URL = "INVALID_GITHUB_URL"
    REPOSITORY_NOT_FOUND = "REPOSITORY_NOT_FOUND"
    REPOSITORY_PRIVATE = "REPOSITORY_PRIVATE"
    GITHUB_RATE_LIMIT = "GITHUB_RATE_LIMIT"
    REPOSITORY_TOO_LARGE = "REPOSITORY_TOO_LARGE"
    TOO_MANY_FILES = "TOO_MANY_FILES"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
    PARSER_FAILED = "PARSER_FAILED"
    RUBRIC_NOT_LOCKED = "RUBRIC_NOT_LOCKED"
    INVALID_RUBRIC = "INVALID_RUBRIC"
    LLM_PROVIDER_FAILED = "LLM_PROVIDER_FAILED"
    INVALID_LLM_OUTPUT = "INVALID_LLM_OUTPUT"
    GRADING_FAILED = "GRADING_FAILED"


class DomainError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def error_response(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


async def domain_exception_handler(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc.code.value, exc.message, exc.details),
    )


async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response(
            ErrorCode.VALIDATION_ERROR.value,
            "Request validation failed.",
            {"errors": exc.errors()},
        ),
    )
