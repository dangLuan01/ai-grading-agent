from dataclasses import dataclass

from app.graders.prompt_loader import PromptLoader, PromptName
from app.graders.schemas import AssignmentAnalysisOutput
from app.llm.router import LLMRouter
from app.models.assignment import Assignment


@dataclass(frozen=True)
class AssignmentAnalysisResult:
    output: AssignmentAnalysisOutput
    prompt_version: str


class AssignmentAnalyzer:
    def __init__(self, prompt_loader: PromptLoader | None = None) -> None:
        self._prompt_loader = prompt_loader or PromptLoader()

    async def analyze(
        self,
        assignment: Assignment,
        llm_router: LLMRouter,
    ) -> AssignmentAnalysisResult:
        prompt = self._prompt_loader.load(PromptName.ASSIGNMENT_ANALYZER)
        output = await llm_router.generate(
            messages=[
                {"role": "system", "content": prompt.text},
                {
                    "role": "user",
                    "content": (
                        "Analyze this assignment and return only the requested JSON.\n\n"
                        f"Title: {assignment.title}\n"
                        f"Description: {assignment.description}\n"
                        f"Total score: {assignment.total_score}"
                    ),
                },
            ],
            response_model=AssignmentAnalysisOutput,
        )
        return AssignmentAnalysisResult(output=output, prompt_version=prompt.version)
