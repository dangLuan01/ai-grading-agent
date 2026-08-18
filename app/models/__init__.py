"""SQLAlchemy model registry."""

from app.models.assignment import Assignment
from app.models.grading import GradingEvidence, GradingResult, GradingRun
from app.models.rubric import Rubric, RubricItem
from app.models.student import Student
from app.models.submission import Submission, SubmissionFile
from app.models.user import User
from app.models.viva import VivaQuestion

__all__ = [
    "Assignment",
    "GradingEvidence",
    "GradingResult",
    "GradingRun",
    "Rubric",
    "RubricItem",
    "Student",
    "Submission",
    "SubmissionFile",
    "User",
    "VivaQuestion",
]
