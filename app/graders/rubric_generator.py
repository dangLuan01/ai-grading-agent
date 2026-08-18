from dataclasses import dataclass

from app.graders.prompt_loader import PromptLoader, PromptName
from app.graders.schemas import AIRubricGenerationOutput, AssignmentAnalysisOutput
from app.llm.router import LLMRouter
from app.models.assignment import Assignment


@dataclass(frozen=True)
class AIRubricGenerationResult:
    output: AIRubricGenerationOutput
    prompt_version: str


class AIRubricGenerator:
    def __init__(self, prompt_loader: PromptLoader | None = None) -> None:
        self._prompt_loader = prompt_loader or PromptLoader()

    async def generate(
        self,
        assignment: Assignment,
        analysis: AssignmentAnalysisOutput,
        llm_router: LLMRouter,
    ) -> AIRubricGenerationResult:
        prompt = self._prompt_loader.load(PromptName.RUBRIC_GENERATOR)
        output = await llm_router.generate(
            messages=[
                {"role": "system", "content": prompt.text},
                {
                    "role": "user",
                    "content": (
                        "Generate a grading rubric derived only from this assignment and "
                        "analysis. Return only JSON matching the schema.\n\n"
                        f"Assignment title: {assignment.title}\n"
                        f"Assignment description: {assignment.description}\n"
                        f"Assignment total score: {assignment.total_score}\n\n"
                        f"Assignment analysis JSON: {analysis.model_dump_json()}"
                    ),
                },
            ],
            response_model=AIRubricGenerationOutput,
        )
        return AIRubricGenerationResult(output=output, prompt_version=prompt.version)
