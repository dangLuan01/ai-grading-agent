from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError, ErrorCode
from app.models.enums import RubricStatus
from app.schemas.assignment import AssignmentCreate
from app.schemas.rubric import RubricCreate, RubricItemCreate
from app.services.assignment_service import assignment_service
from app.services.rubric_service import rubric_service


def rubric_item(
    criterion: str,
    description: str,
    max_score: str,
) -> RubricItemCreate:
    return RubricItemCreate(
        criterion=criterion,
        description=description,
        max_score=Decimal(max_score),
    )


def test_deterministic_validation_reports_invalid_rubric() -> None:
    issues = rubric_service.validate_items(
        Decimal("100.00"),
        [
            rubric_item("", "Has no criterion", "50"),
            rubric_item("Design", "", "0"),
            rubric_item("Design", "Duplicate criterion", "-5"),
        ],
    )

    codes = {issue.code for issue in issues}
    assert "EMPTY_CRITERION" in codes
    assert "MISSING_DESCRIPTION" in codes
    assert "NON_POSITIVE_MAX_SCORE" in codes
    assert "DUPLICATE_CRITERION" in codes
    assert "TOTAL_SCORE_MISMATCH" in codes


def test_deterministic_validation_rejects_empty_rubric() -> None:
    issues = rubric_service.validate_items(Decimal("100.00"), [])

    codes = {issue.code for issue in issues}
    assert "RUBRIC_EMPTY" in codes
    assert "TOTAL_SCORE_MISMATCH" in codes


def test_replace_locked_rubric_items_rejects_in_place_mutation(
    db_session: Session,
    user_factory,
) -> None:
    teacher = user_factory()
    assignment = assignment_service.create_assignment(
        db_session,
        AssignmentCreate(
            title="System analysis",
            description="Analyze appointment scheduling requirements.",
            total_score=Decimal("100.00"),
        ),
        created_by=teacher.id,
    )
    rubric_service.create_manual_rubric(
        db_session,
        assignment.id,
        RubricCreate(
            items=[
                rubric_item("Requirements", "Identifies requirements.", "60"),
                rubric_item("Clarity", "Communicates clearly.", "40"),
            ]
        ),
    )
    locked = rubric_service.lock_latest_rubric(db_session, assignment.id)

    with pytest.raises(DomainError) as exc_info:
        rubric_service.replace_rubric_items(
            db_session,
            locked,
            [rubric_item("Changed", "Should not mutate locked rubric.", "100")],
        )

    assert exc_info.value.code == ErrorCode.RUBRIC_LOCKED
    assert locked.status == RubricStatus.LOCKED.value
