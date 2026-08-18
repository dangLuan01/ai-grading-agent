from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fastapi import status
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError, ErrorCode
from app.graders.assignment_analyzer import AssignmentAnalyzer
from app.graders.rubric_generator import AIRubricGenerator
from app.graders.rubric_validator import AIRubricValidator
from app.graders.schemas import AIRubricValidationOutput, AssignmentAnalysisOutput
from app.llm.router import LLMRouter
from app.models.enums import RubricSource
from app.models.rubric import Rubric
from app.schemas.rubric import RubricItemCreate
from app.services.assignment_service import assignment_service
from app.services.rubric_service import rubric_service


@dataclass(frozen=True)
class AIRubricGenerationServiceResult:
    rubric: Rubric
    analysis: AssignmentAnalysisOutput
    ai_validation: AIRubricValidationOutput
    prompt_versions: dict[str, str]


@dataclass(frozen=True)
class AIRubricValidationServiceResult:
    output: AIRubricValidationOutput
    prompt_version: str


@dataclass(frozen=True)
class TransientRubricItem:
    criterion: str
    description: str
    max_score: Decimal
    evaluation_guide: dict[str, Any]
    expected_evidence: list[Any]


@dataclass(frozen=True)
class TransientRubric:
    source: str
    version: int
    items: list[TransientRubricItem]


class AIRubricService:
    def __init__(
        self,
        *,
        analyzer: AssignmentAnalyzer | None = None,
        generator: AIRubricGenerator | None = None,
        validator: AIRubricValidator | None = None,
    ) -> None:
        self._analyzer = analyzer or AssignmentAnalyzer()
        self._generator = generator or AIRubricGenerator()
        self._validator = validator or AIRubricValidator()

    async def generate_rubric(
        self,
        db: Session,
        assignment_id: int,
        llm_router: LLMRouter,
    ) -> AIRubricGenerationServiceResult:
        assignment = rubric_service.ensure_initial_rubric_can_be_created(db, assignment_id)
        analysis_result = await self._analyzer.analyze(assignment, llm_router)
        generation_result = await self._generator.generate(
            assignment,
            analysis_result.output,
            llm_router,
        )
        rubric_items = [
            RubricItemCreate(
                criterion=item.criterion,
                description=item.description,
                max_score=item.max_score,
                evaluation_guide=item.evaluation_guide,
                expected_evidence=item.expected_evidence,
            )
            for item in generation_result.output.rubric
        ]
        rubric_service.ensure_items_valid(assignment, rubric_items)
        transient_rubric = TransientRubric(
            source=RubricSource.AI_GENERATED.value,
            version=1,
            items=[
                TransientRubricItem(
                    criterion=item.criterion,
                    description=item.description,
                    max_score=item.max_score,
                    evaluation_guide=item.evaluation_guide,
                    expected_evidence=item.expected_evidence,
                )
                for item in rubric_items
            ],
        )
        ai_validation_result = await self._validator.validate(
            assignment,
            transient_rubric,
            llm_router,
        )
        if not ai_validation_result.output.valid:
            raise DomainError(
                ErrorCode.INVALID_RUBRIC,
                "AI rubric quality validation failed.",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={
                    "ai_valid": False,
                    "warnings": [
                        warning.model_dump()
                        for warning in ai_validation_result.output.warnings
                    ],
                    "ai_prompt_version": ai_validation_result.prompt_version,
                },
            )
        rubric = rubric_service.create_ai_generated_rubric(db, assignment_id, rubric_items)
        return AIRubricGenerationServiceResult(
            rubric=rubric,
            analysis=analysis_result.output,
            ai_validation=ai_validation_result.output,
            prompt_versions={
                "assignment_analyzer": analysis_result.prompt_version,
                "rubric_generator": generation_result.prompt_version,
                "rubric_validator": ai_validation_result.prompt_version,
            },
        )

    async def validate_latest_rubric(
        self,
        db: Session,
        assignment_id: int,
        llm_router: LLMRouter,
    ) -> AIRubricValidationServiceResult:
        assignment = assignment_service.get_assignment(db, assignment_id)
        rubric = rubric_service.get_latest_rubric(db, assignment_id)
        validation_result = await self._validator.validate(assignment, rubric, llm_router)
        return AIRubricValidationServiceResult(
            output=validation_result.output,
            prompt_version=validation_result.prompt_version,
        )


ai_rubric_service = AIRubricService()
