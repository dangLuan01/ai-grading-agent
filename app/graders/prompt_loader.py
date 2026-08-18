from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class PromptName(StrEnum):
    ASSIGNMENT_ANALYZER = "assignment_analyzer"
    RUBRIC_GENERATOR = "rubric_generator"
    RUBRIC_VALIDATOR = "rubric_validator"


@dataclass(frozen=True)
class PromptTemplate:
    name: PromptName
    version: str
    text: str
    path: Path


class PromptLoader:
    def __init__(self, prompts_dir: Path | None = None) -> None:
        self._prompts_dir = prompts_dir or Path(__file__).resolve().parents[2] / "prompts"

    def load(self, name: PromptName, *, version: str = "v1") -> PromptTemplate:
        path = self._prompts_dir / f"{name.value}_{version}.txt"
        if not path.is_file():
            raise FileNotFoundError(f"Prompt file was not found: {path}")
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"Prompt file is empty: {path}")
        return PromptTemplate(name=name, version=version, text=text, path=path)
