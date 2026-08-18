from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from fastapi import status
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError, ErrorCode
from app.models.assignment import Assignment
from app.models.enums import RubricSource, RubricStatus
from app.models.rubric import Rubric
from app.repositories.rubric_repository import rubric_repository
from app.schemas.rubric import RubricCreate, RubricItemCreate, RubricUpdate
from app.services.assignment_service import assignment_service


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class RubricService:
    def create_manual_rubric(
        self,
        db: Session,
        assignment_id: int,
        payload: RubricCreate,
    ) -> Rubric:
        return self._create_initial_rubric(
            db,
            assignment_id,
            payload.items,
            source=RubricSource.TEACHER_PROVIDED.value,
        )

    def create_ai_generated_rubric(
        self,
        db: Session,
        assignment_id: int,
        items: list[RubricItemCreate],
    ) -> Rubric:
        return self._create_initial_rubric(
            db,
            assignment_id,
            items,
            source=RubricSource.AI_GENERATED.value,
        )

    def _create_initial_rubric(
        self,
        db: Session,
        assignment_id: int,
        items: list[RubricItemCreate],
        *,
        source: str,
    ) -> Rubric:
        assignment = self.ensure_initial_rubric_can_be_created(db, assignment_id)
        self._raise_if_invalid(assignment, items)
        return rubric_repository.create(
            db,
            assignment_id=assignment_id,
            version=1,
            source=source,
            items=items,
        )

    def ensure_initial_rubric_can_be_created(
        self,
        db: Session,
        assignment_id: int,
    ) -> Assignment:
        assignment = assignment_service.get_assignment(db, assignment_id)
        self._ensure_assignment_is_editable(assignment)

        existing = rubric_repository.get_latest_for_assignment(db, assignment_id)
        if existing is not None:
            raise DomainError(
                ErrorCode.RUBRIC_DRAFT_EXISTS,
                "Assignment already has a rubric. Use PUT to edit a draft or create a new version.",
                status_code=status.HTTP_409_CONFLICT,
                details={"assignment_id": assignment_id, "rubric_id": existing.id},
            )
        return assignment

    def get_latest_rubric(self, db: Session, assignment_id: int) -> Rubric:
        assignment_service.get_assignment(db, assignment_id)
        rubric = rubric_repository.get_latest_for_assignment(db, assignment_id)
        if rubric is None:
            raise DomainError(
                ErrorCode.RUBRIC_NOT_FOUND,
                "Rubric was not found for this assignment.",
                status_code=status.HTTP_404_NOT_FOUND,
                details={"assignment_id": assignment_id},
            )
        return rubric

    def update_latest_rubric(
        self,
        db: Session,
        assignment_id: int,
        payload: RubricUpdate,
    ) -> Rubric:
        assignment = assignment_service.get_assignment(db, assignment_id)
        self._ensure_assignment_is_editable(assignment)
        self._raise_if_invalid(assignment, payload.items)

        latest = rubric_repository.get_latest_for_assignment(db, assignment_id)
        if latest is None:
            return rubric_repository.create(
                db,
                assignment_id=assignment_id,
                version=1,
                source=RubricSource.TEACHER_PROVIDED.value,
                items=payload.items,
            )

        if latest.status == RubricStatus.DRAFT.value:
            source = self._source_after_teacher_edit(latest.source)
            return self.replace_rubric_items(db, latest, payload.items, source=source)

        if latest.status == RubricStatus.LOCKED.value:
            source = self._source_after_teacher_edit(latest.source)
            return rubric_repository.create(
                db,
                assignment_id=assignment_id,
                version=rubric_repository.next_version(db, assignment_id),
                source=source,
                items=payload.items,
            )

        raise DomainError(
            ErrorCode.RUBRIC_NOT_FOUND,
            "No editable rubric version is available.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"assignment_id": assignment_id},
        )

    def replace_rubric_items(
        self,
        db: Session,
        rubric: Rubric,
        items: list[RubricItemCreate],
        *,
        source: str | None = None,
    ) -> Rubric:
        if rubric.status != RubricStatus.DRAFT.value:
            raise DomainError(
                ErrorCode.RUBRIC_LOCKED,
                "Locked rubrics cannot be modified in place.",
                status_code=status.HTTP_409_CONFLICT,
                details={"rubric_id": rubric.id, "status": rubric.status},
            )
        return rubric_repository.replace_items(db, rubric, items, source=source)

    def validate_latest_rubric(self, db: Session, assignment_id: int) -> list[ValidationIssue]:
        assignment = assignment_service.get_assignment(db, assignment_id)
        rubric = self.get_latest_rubric(db, assignment_id)
        return self.validate_items(assignment.total_score, list(rubric.items))

    def ensure_items_valid(self, assignment: Assignment, items: list[Any]) -> None:
        self._raise_if_invalid(assignment, items)

    def lock_latest_rubric(self, db: Session, assignment_id: int) -> Rubric:
        assignment = assignment_service.get_assignment(db, assignment_id)
        rubric = self.get_latest_rubric(db, assignment_id)

        if rubric.status != RubricStatus.DRAFT.value:
            raise DomainError(
                ErrorCode.RUBRIC_NOT_DRAFT,
                "Only draft rubrics can be locked.",
                status_code=status.HTTP_409_CONFLICT,
                details={"rubric_id": rubric.id, "status": rubric.status},
            )

        self._raise_if_invalid(assignment, list(rubric.items))
        return rubric_repository.lock(db, rubric)

    def validate_items(
        self,
        assignment_total_score: Decimal,
        items: list[Any],
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        total_score = Decimal("0")
        seen_criteria: dict[str, int] = {}

        if not items:
            issues.append(
                ValidationIssue(
                    code="RUBRIC_EMPTY",
                    message="Rubric must contain at least one criterion.",
                )
            )

        for index, item in enumerate(items):
            criterion = str(getattr(item, "criterion", "") or "").strip()
            description = str(getattr(item, "description", "") or "").strip()
            max_score = getattr(item, "max_score", None)

            if not criterion:
                issues.append(
                    ValidationIssue(
                        code="EMPTY_CRITERION",
                        message="Rubric criterion must not be empty.",
                        details={"index": index},
                    )
                )
            else:
                normalized = " ".join(criterion.casefold().split())
                if normalized in seen_criteria:
                    issues.append(
                        ValidationIssue(
                            code="DUPLICATE_CRITERION",
                            message="Rubric criteria must be unique.",
                            details={
                                "index": index,
                                "first_index": seen_criteria[normalized],
                                "criterion": criterion,
                            },
                        )
                    )
                else:
                    seen_criteria[normalized] = index

            if not description:
                issues.append(
                    ValidationIssue(
                        code="MISSING_DESCRIPTION",
                        message="Rubric item description must not be empty.",
                        details={"index": index},
                    )
                )

            try:
                score = Decimal(str(max_score))
            except Exception:
                issues.append(
                    ValidationIssue(
                        code="INVALID_MAX_SCORE",
                        message="Rubric item max_score must be a valid number.",
                        details={"index": index},
                    )
                )
                continue

            total_score += score
            if score <= 0:
                issues.append(
                    ValidationIssue(
                        code="NON_POSITIVE_MAX_SCORE",
                        message="Rubric item max_score must be greater than zero.",
                        details={"index": index, "max_score": str(score)},
                    )
                )

        if total_score != assignment_total_score:
            issues.append(
                ValidationIssue(
                    code="TOTAL_SCORE_MISMATCH",
                    message="Rubric item scores must sum to the assignment total score.",
                    details={
                        "rubric_total_score": str(total_score),
                        "assignment_total_score": str(assignment_total_score),
                    },
                )
            )

        return issues

    def _raise_if_invalid(self, assignment: Assignment, items: list[Any]) -> None:
        issues = self.validate_items(assignment.total_score, items)
        if issues:
            raise DomainError(
                ErrorCode.INVALID_RUBRIC,
                "Rubric deterministic validation failed.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"errors": [issue.as_dict() for issue in issues]},
            )

    def _ensure_assignment_is_editable(self, assignment: Assignment) -> None:
        if assignment.status == "ARCHIVED":
            raise DomainError(
                ErrorCode.ASSIGNMENT_ARCHIVED,
                "Archived assignments cannot be modified.",
                status_code=status.HTTP_409_CONFLICT,
                details={"assignment_id": assignment.id},
            )

    def _source_after_teacher_edit(self, current_source: str) -> str:
        if current_source == RubricSource.AI_GENERATED.value:
            return RubricSource.AI_GENERATED_TEACHER_EDITED.value
        return current_source or RubricSource.TEACHER_PROVIDED.value


rubric_service = RubricService()
