from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.assignment import AssignmentCreate, AssignmentRead, AssignmentUpdate
from app.services.assignment_service import assignment_service

router = APIRouter(prefix="/assignments", tags=["Assignments"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    payload: AssignmentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    return assignment_service.create_assignment(db, payload, created_by=current_user.id)


@router.get("", response_model=list[AssignmentRead])
async def list_assignments(
    db: DbSession,
    _current_user: CurrentUser,
    include_archived: bool = Query(default=False),
):
    return assignment_service.list_assignments(db, include_archived=include_archived)


@router.get("/{assignment_id}", response_model=AssignmentRead)
async def get_assignment(
    assignment_id: int,
    db: DbSession,
    _current_user: CurrentUser,
):
    return assignment_service.get_assignment(db, assignment_id)


@router.patch("/{assignment_id}", response_model=AssignmentRead)
async def update_assignment(
    assignment_id: int,
    payload: AssignmentUpdate,
    db: DbSession,
    _current_user: CurrentUser,
):
    return assignment_service.update_assignment(db, assignment_id, payload)


@router.delete("/{assignment_id}", response_model=AssignmentRead)
async def delete_assignment(
    assignment_id: int,
    db: DbSession,
    _current_user: CurrentUser,
):
    return assignment_service.archive_assignment(db, assignment_id)
