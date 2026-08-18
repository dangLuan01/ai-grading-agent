from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.rubric import (
    RubricCreate,
    RubricRead,
    RubricUpdate,
    RubricValidationIssue,
    RubricValidationResponse,
)
from app.services.rubric_service import rubric_service

router = APIRouter(prefix="/assignments/{assignment_id}/rubric", tags=["Rubrics"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=RubricRead, status_code=status.HTTP_201_CREATED)
async def create_manual_rubric(
    assignment_id: int,
    payload: RubricCreate,
    db: DbSession,
    _current_user: CurrentUser,
):
    return rubric_service.create_manual_rubric(db, assignment_id, payload)


@router.get("", response_model=RubricRead)
async def get_latest_rubric(
    assignment_id: int,
    db: DbSession,
    _current_user: CurrentUser,
):
    return rubric_service.get_latest_rubric(db, assignment_id)


@router.put("", response_model=RubricRead)
async def update_latest_rubric(
    assignment_id: int,
    payload: RubricUpdate,
    db: DbSession,
    _current_user: CurrentUser,
):
    return rubric_service.update_latest_rubric(db, assignment_id, payload)


@router.post("/validate", response_model=RubricValidationResponse)
async def validate_latest_rubric(
    assignment_id: int,
    db: DbSession,
    _current_user: CurrentUser,
):
    errors = rubric_service.validate_latest_rubric(db, assignment_id)
    return RubricValidationResponse(
        valid=not errors,
        errors=[RubricValidationIssue(**error.as_dict()) for error in errors],
    )


@router.post("/lock", response_model=RubricRead)
async def lock_latest_rubric(
    assignment_id: int,
    db: DbSession,
    _current_user: CurrentUser,
):
    return rubric_service.lock_latest_rubric(db, assignment_id)
