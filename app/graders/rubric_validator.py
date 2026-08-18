import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from app.graders.prompt_loader import PromptLoader, PromptName
from app.graders.schemas import AIRubricValidationOutput
from app.llm.router import LLMRouter
from app.models.assignment import Assignment


class RubricItemForValidation(Protocol):
    criterion: str
    description: str
    max_score: Decimal
    evaluation_guide: dict[str, Any]
    expected_evidence: list[Any]


class RubricForValidation(Protocol):
    source: str
    version: int
    items: Sequence[RubricItemForValidation]


@dataclass(frozen=True)
class AIRubricValidationResult:
    output: AIRubricValidationOutput
    prompt_version: str


class AIRubricValidator:
    def __init__(self, prompt_loader: PromptLoader | None = None) -> None:
        self._prompt_loader = prompt_loader or PromptLoader()

    async def validate(
        self,
        assignment: Assignment,
        rubric: RubricForValidation,
        llm_router: LLMRouter,
    ) -> AIRubricValidationResult:
        prompt = self._prompt_loader.load(PromptName.RUBRIC_VALIDATOR)
        rubric_payload = [
            {
                "criterion": item.criterion,
                "description": item.description,
                "max_score": str(item.max_score),
                "evaluation_guide": item.evaluation_guide,
                "expected_evidence": item.expected_evidence,
            }
            for item in rubric.items
        ]
        rubric_json = json.dumps(rubric_payload, default=str)
        output = await llm_router.generate(
            messages=[
                {"role": "system", "content": prompt.text},
                {
                    "role": "user",
                    "content": (
                        "Review this rubric against the assignment. Return warnings only; "
                        "do not rewrite or correct the rubric.\n\n"
                        f"Assignment title: {assignment.title}\n"
                        f"Assignment description: {assignment.description}\n"
                        f"Assignment total score: {assignment.total_score}\n\n"
                        f"Rubric source: {rubric.source}\n"
                        f"Rubric version: {rubric.version}\n"
                        f"Rubric JSON: {rubric_json}"
                    ),
                },
            ],
            response_model=AIRubricValidationOutput,
        )
        return AIRubricValidationResult(output=output, prompt_version=prompt.version)
