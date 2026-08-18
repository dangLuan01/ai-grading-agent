from decimal import Decimal

from fastapi import status
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError, ErrorCode
from app.models.assignment import Assignment
from app.repositories.assignment_repository import assignment_repository
from app.schemas.assignment import AssignmentCreate, AssignmentUpdate


class AssignmentService:
    def create_assignment(
        self,
        db: Session,
        payload: AssignmentCreate,
        *,
        created_by: int,
    ) -> Assignment:
        return assignment_repository.create(
            db,
            title=payload.title,
            description=payload.description,
            total_score=payload.total_score,
            created_by=created_by,
        )

    def list_assignments(self, db: Session, *, include_archived: bool = False) -> list[Assignment]:
        return assignment_repository.list(db, include_archived=include_archived)

    def get_assignment(self, db: Session, assignment_id: int) -> Assignment:
        assignment = assignment_repository.get(db, assignment_id)
        if assignment is None:
            raise DomainError(
                ErrorCode.ASSIGNMENT_NOT_FOUND,
                "Assignment was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
                details={"assignment_id": assignment_id},
            )
        return assignment

    def update_assignment(
        self,
        db: Session,
        assignment_id: int,
        payload: AssignmentUpdate,
    ) -> Assignment:
        assignment = self.get_assignment(db, assignment_id)
        update_data = payload.model_dump(exclude_unset=True)

        total_score = update_data.get("total_score")
        if total_score is not None and assignment_repository.has_locked_rubric(db, assignment_id):
            raise DomainError(
                ErrorCode.INVALID_RUBRIC,
                "Assignment total score cannot be changed after a rubric is locked.",
                status_code=status.HTTP_409_CONFLICT,
                details={"assignment_id": assignment_id},
            )

        return assignment_repository.update(
            db,
            assignment,
            title=update_data.get("title"),
            description=update_data.get("description"),
            total_score=total_score if isinstance(total_score, Decimal) else None,
            status=update_data.get("status"),
        )

    def archive_assignment(self, db: Session, assignment_id: int) -> Assignment:
        assignment = self.get_assignment(db, assignment_id)
        return assignment_repository.archive(db, assignment)


assignment_service = AssignmentService()
