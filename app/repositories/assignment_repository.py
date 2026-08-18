from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.assignment import Assignment
from app.models.enums import AssignmentStatus
from app.models.rubric import Rubric
from app.models.submission import Submission


class AssignmentRepository:
    def create(
        self,
        db: Session,
        *,
        title: str,
        description: str,
        total_score: Decimal,
        created_by: int,
    ) -> Assignment:
        assignment = Assignment(
            title=title.strip(),
            description=description.strip(),
            total_score=total_score,
            created_by=created_by,
            status=AssignmentStatus.DRAFT.value,
        )
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
        return assignment

    def list(self, db: Session, *, include_archived: bool = False) -> list[Assignment]:
        statement = select(Assignment).order_by(Assignment.id)
        if not include_archived:
            statement = statement.where(Assignment.status != AssignmentStatus.ARCHIVED.value)
        return list(db.execute(statement).scalars().all())

    def get(self, db: Session, assignment_id: int) -> Assignment | None:
        return db.get(Assignment, assignment_id)

    def update(
        self,
        db: Session,
        assignment: Assignment,
        *,
        title: str | None = None,
        description: str | None = None,
        total_score: Decimal | None = None,
        status: AssignmentStatus | None = None,
    ) -> Assignment:
        if title is not None:
            assignment.title = title.strip()
        if description is not None:
            assignment.description = description.strip()
        if total_score is not None:
            assignment.total_score = total_score
        if status is not None:
            assignment.status = status.value
        db.commit()
        db.refresh(assignment)
        return assignment

    def archive(self, db: Session, assignment: Assignment) -> Assignment:
        assignment.status = AssignmentStatus.ARCHIVED.value
        db.commit()
        db.refresh(assignment)
        return assignment

    def has_business_data(self, db: Session, assignment_id: int) -> bool:
        rubric_count = db.scalar(
            select(func.count()).select_from(Rubric).where(Rubric.assignment_id == assignment_id)
        )
        submission_count = db.scalar(
            select(func.count())
            .select_from(Submission)
            .where(Submission.assignment_id == assignment_id)
        )
        return bool(rubric_count or submission_count)

    def has_locked_rubric(self, db: Session, assignment_id: int) -> bool:
        count = db.scalar(
            select(func.count())
            .select_from(Rubric)
            .where(
                Rubric.assignment_id == assignment_id,
                Rubric.status == "LOCKED",
            )
        )
        return bool(count)


assignment_repository = AssignmentRepository()
