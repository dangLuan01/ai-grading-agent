from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError, ErrorCode
from app.graders.assignment_analyzer import AssignmentAnalyzer
from app.graders.prompt_loader import PromptLoader, PromptName
from app.graders.rubric_generator import AIRubricGenerator
from app.graders.rubric_validator import AIRubricValidator
from app.llm.fake_provider import FakeLLMProvider
from app.llm.router import LLMRouter
from app.models.enums import RubricSource, RubricStatus
from app.schemas.assignment import AssignmentCreate
from app.schemas.rubric import RubricCreate, RubricItemCreate
from app.services.ai_rubric_service import AIRubricService
from app.services.assignment_service import assignment_service
from app.services.rubric_service import rubric_service


def make_assignment(db_session: Session, user_factory):
    teacher = user_factory(email="phase4-teacher@example.com")
    return assignment_service.create_assignment(
        db_session,
        AssignmentCreate(
            title="Requirements analysis",
            description="Analyze appointment scheduling requirements and present findings.",
            total_score=Decimal("100.00"),
        ),
        created_by=teacher.id,
    )


def valid_items() -> list[RubricItemCreate]:
    return [
        RubricItemCreate(
            criterion="Requirements coverage",
            description="Identifies functional requirements.",
            max_score=Decimal("60"),
            evaluation_guide={"excellent": "Complete coverage."},
            expected_evidence=["Functional requirements"],
        ),
        RubricItemCreate(
            criterion="Clarity",
            description="Communicates the analysis clearly.",
            max_score=Decimal("40"),
            evaluation_guide={"excellent": "Clear and organized."},
            expected_evidence=["Structured report"],
        ),
    ]


def llm_router(*responses: dict | str) -> tuple[LLMRouter, FakeLLMProvider]:
    fake = FakeLLMProvider(responses=list(responses))
    return LLMRouter(primary_provider=fake), fake


def valid_ai_quality_response(warnings: list[dict] | None = None) -> dict:
    return {"valid": True, "warnings": warnings or []}


def test_prompt_loader_loads_versioned_phase4_prompts() -> None:
    loader = PromptLoader()

    analyzer_prompt = loader.load(PromptName.ASSIGNMENT_ANALYZER)
    generator_prompt = loader.load(PromptName.RUBRIC_GENERATOR)
    validator_prompt = loader.load(PromptName.RUBRIC_VALIDATOR)

    assert analyzer_prompt.version == "v1"
    assert "academic assignment analysis engine" in analyzer_prompt.text
    assert generator_prompt.version == "v1"
    assert "Total max score" in generator_prompt.text
    assert validator_prompt.version == "v1"
    assert "warnings only" in validator_prompt.text


async def test_assignment_analyzer_returns_structured_output(
    db_session: Session,
    user_factory,
) -> None:
    assignment = make_assignment(db_session, user_factory)
    router, fake = llm_router(
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Analyze scheduling requirements"],
            "expected_outputs": ["Requirements report"],
            "constraints": ["Submit a PDF report"],
        }
    )

    result = await AssignmentAnalyzer().analyze(assignment, router)

    assert result.prompt_version == "v1"
    assert result.output.assignment_type == "requirements_analysis"
    assert result.output.requirements == ["Analyze scheduling requirements"]
    assert result.output.constraints == ["Submit a PDF report"]
    assert fake.call_count == 1
    assert "Title: Requirements analysis" in fake.seen_messages[0][1].content


async def test_assignment_analyzer_does_not_invent_constraints_from_controlled_output(
    db_session: Session,
    user_factory,
) -> None:
    assignment = make_assignment(db_session, user_factory)
    router, _fake = llm_router(
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Analyze scheduling requirements"],
            "expected_outputs": ["Requirements report"],
            "constraints": [],
        }
    )

    result = await AssignmentAnalyzer().analyze(assignment, router)

    assert result.output.constraints == []


async def test_ai_rubric_generator_returns_structured_output(
    db_session: Session,
    user_factory,
) -> None:
    assignment = make_assignment(db_session, user_factory)
    analysis_router, _ = llm_router(
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Analyze scheduling requirements"],
            "expected_outputs": ["Requirements report"],
            "constraints": ["Submit a PDF report"],
        }
    )
    analysis = (await AssignmentAnalyzer().analyze(assignment, analysis_router)).output
    router, fake = llm_router(
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Analyze scheduling requirements"],
            "rubric": [
                {
                    "criterion": "Requirements coverage",
                    "description": "Covers the stated requirements.",
                    "max_score": "100",
                    "evaluation_guide": {"excellent": "Complete and precise."},
                    "expected_evidence": ["Requirement list"],
                }
            ],
        }
    )

    result = await AIRubricGenerator().generate(assignment, analysis, router)

    assert result.prompt_version == "v1"
    assert result.output.rubric[0].criterion == "Requirements coverage"
    assert result.output.rubric[0].max_score == Decimal("100")
    assert fake.call_count == 1
    assert "Assignment total score: 100.00" in fake.seen_messages[0][1].content
    assert "Submit a PDF report" in fake.seen_messages[0][1].content


async def test_ai_rubric_validator_returns_warnings_without_mutation(
    db_session: Session,
    user_factory,
) -> None:
    assignment = make_assignment(db_session, user_factory)
    rubric = rubric_service.create_manual_rubric(
        db_session,
        assignment.id,
        RubricCreate(items=valid_items()),
    )
    router, fake = llm_router(
        {
            "valid": True,
            "warnings": [
                {
                    "code": "MISSING_COVERAGE",
                    "message": "Confirm reporting constraints are covered.",
                    "criterion": None,
                }
            ],
        }
    )

    result = await AIRubricValidator().validate(assignment, rubric, router)

    assert result.prompt_version == "v1"
    assert result.output.warnings[0].code == "MISSING_COVERAGE"
    assert fake.call_count == 1
    db_session.expire_all()
    unchanged = rubric_service.get_latest_rubric(db_session, assignment.id)
    assert unchanged.source == RubricSource.TEACHER_PROVIDED.value
    assert unchanged.items[0].description == "Identifies functional requirements."


async def test_ai_rubric_service_persists_valid_generated_draft(
    db_session: Session,
    user_factory,
) -> None:
    assignment = make_assignment(db_session, user_factory)
    router, _fake = llm_router(
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Analyze scheduling requirements"],
            "expected_outputs": ["Requirements report"],
            "constraints": ["Submit a PDF report"],
        },
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Analyze scheduling requirements"],
            "rubric": [
                {
                    "criterion": "Requirements coverage",
                    "description": "Covers the requested requirements.",
                    "max_score": "60",
                    "evaluation_guide": {"excellent": "Complete."},
                    "expected_evidence": ["Requirement list"],
                },
                {
                    "criterion": "Clarity",
                    "description": "Presents findings clearly.",
                    "max_score": "40",
                    "evaluation_guide": {"excellent": "Clear."},
                    "expected_evidence": ["Structured report"],
                },
            ],
        },
        valid_ai_quality_response(),
    )

    result = await AIRubricService().generate_rubric(db_session, assignment.id, router)

    assert result.rubric.source == RubricSource.AI_GENERATED.value
    assert result.rubric.status == RubricStatus.DRAFT.value
    assert result.rubric.version == 1
    assert result.prompt_versions == {
        "assignment_analyzer": "v1",
        "rubric_generator": "v1",
        "rubric_validator": "v1",
    }
    assert result.ai_validation.valid is True


async def test_ai_rubric_service_invokes_quality_validator_before_persistence(
    db_session: Session,
    user_factory,
) -> None:
    assignment = make_assignment(db_session, user_factory)
    router, fake = llm_router(
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Analyze scheduling requirements"],
            "expected_outputs": ["Requirements report"],
            "constraints": [],
        },
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Analyze scheduling requirements"],
            "rubric": [
                {
                    "criterion": "Requirements coverage",
                    "description": "Covers the requested requirements.",
                    "max_score": "100",
                    "evaluation_guide": {},
                    "expected_evidence": ["Requirement list"],
                }
            ],
        },
        valid_ai_quality_response(),
    )

    await AIRubricService().generate_rubric(db_session, assignment.id, router)

    assert fake.call_count == 3
    assert "Rubric source: AI_GENERATED" in fake.seen_messages[2][1].content
    saved = rubric_service.get_latest_rubric(db_session, assignment.id)
    assert saved.source == RubricSource.AI_GENERATED.value


async def test_ai_rubric_service_rejects_serious_ai_quality_failure_without_persisting(
    db_session: Session,
    user_factory,
) -> None:
    assignment = make_assignment(db_session, user_factory)
    router, fake = llm_router(
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Analyze scheduling requirements"],
            "expected_outputs": ["Requirements report"],
            "constraints": [],
        },
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Analyze scheduling requirements"],
            "rubric": [
                {
                    "criterion": "Unrelated mobile app implementation",
                    "description": "Grades work not requested by the assignment.",
                    "max_score": "100",
                    "evaluation_guide": {},
                    "expected_evidence": ["Mobile app source code"],
                }
            ],
        },
        {
            "valid": False,
            "warnings": [
                {
                    "code": "UNSUPPORTED_CRITERION",
                    "message": "The rubric adds implementation work absent from the assignment.",
                    "criterion": "Unrelated mobile app implementation",
                }
            ],
        },
    )

    with pytest.raises(DomainError) as exc_info:
        await AIRubricService().generate_rubric(db_session, assignment.id, router)

    assert exc_info.value.code == ErrorCode.INVALID_RUBRIC
    assert exc_info.value.details["ai_valid"] is False
    assert exc_info.value.details["warnings"][0]["code"] == "UNSUPPORTED_CRITERION"
    assert fake.call_count == 3
    with pytest.raises(DomainError):
        rubric_service.get_latest_rubric(db_session, assignment.id)


async def test_ai_rubric_service_persists_draft_with_non_critical_warnings(
    db_session: Session,
    user_factory,
) -> None:
    assignment = make_assignment(db_session, user_factory)
    router, _fake = llm_router(
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Analyze scheduling requirements"],
            "expected_outputs": ["Requirements report"],
            "constraints": [],
        },
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Analyze scheduling requirements"],
            "rubric": [
                {
                    "criterion": "Requirements coverage",
                    "description": "Covers the requested requirements.",
                    "max_score": "100",
                    "evaluation_guide": {},
                    "expected_evidence": ["Requirement list"],
                }
            ],
        },
        valid_ai_quality_response(
            [
                {
                    "code": "REVIEW_AMBIGUITY",
                    "message": "Teacher should confirm expected level of detail.",
                    "criterion": "Requirements coverage",
                }
            ]
        ),
    )

    result = await AIRubricService().generate_rubric(db_session, assignment.id, router)

    assert result.rubric.status == RubricStatus.DRAFT.value
    assert result.ai_validation.valid is True
    assert result.ai_validation.warnings[0].code == "REVIEW_AMBIGUITY"


async def test_ai_rubric_service_rejects_generated_rubric_with_wrong_total(
    db_session: Session,
    user_factory,
) -> None:
    assignment = make_assignment(db_session, user_factory)
    router, _fake = llm_router(
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Analyze scheduling requirements"],
            "expected_outputs": ["Requirements report"],
            "constraints": [],
        },
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Analyze scheduling requirements"],
            "rubric": [
                {
                    "criterion": "Requirements coverage",
                    "description": "Covers the requested requirements.",
                    "max_score": "90",
                    "evaluation_guide": {},
                    "expected_evidence": ["Requirement list"],
                }
            ],
        },
    )

    with pytest.raises(DomainError) as exc_info:
        await AIRubricService().generate_rubric(db_session, assignment.id, router)

    assert exc_info.value.code == ErrorCode.INVALID_RUBRIC
    with pytest.raises(DomainError) as not_found:
        rubric_service.get_latest_rubric(db_session, assignment.id)
    assert not_found.value.code == ErrorCode.RUBRIC_NOT_FOUND


async def test_ai_rubric_service_rejects_generation_when_rubric_exists_before_llm_call(
    db_session: Session,
    user_factory,
) -> None:
    assignment = make_assignment(db_session, user_factory)
    rubric_service.create_manual_rubric(
        db_session,
        assignment.id,
        RubricCreate(items=valid_items()),
    )
    router, fake = llm_router(
        {
            "assignment_type": "requirements_analysis",
            "requirements": ["Should not be called"],
            "expected_outputs": [],
            "constraints": [],
        }
    )

    with pytest.raises(DomainError) as exc_info:
        await AIRubricService().generate_rubric(db_session, assignment.id, router)

    assert exc_info.value.code == ErrorCode.RUBRIC_DRAFT_EXISTS
    assert fake.call_count == 0
