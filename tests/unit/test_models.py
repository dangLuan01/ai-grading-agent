from sqlalchemy import JSON, Numeric

from app import models as _models  # noqa: F401
from app.db.base import Base


def test_phase1_metadata_contains_foundation_tables() -> None:
    expected_tables = {
        "users",
        "assignments",
        "rubrics",
        "rubric_items",
        "students",
        "submissions",
        "submission_files",
        "grading_runs",
        "grading_results",
        "grading_evidence",
        "viva_questions",
    }

    assert expected_tables.issubset(set(Base.metadata.tables))


def test_json_and_score_columns_use_portable_sqlalchemy_types() -> None:
    rubric_items = Base.metadata.tables["rubric_items"]
    grading_results = Base.metadata.tables["grading_results"]

    assert isinstance(rubric_items.c.evaluation_guide.type, JSON)
    assert isinstance(rubric_items.c.expected_evidence.type, JSON)
    assert isinstance(grading_results.c.issues.type, JSON)
    assert isinstance(rubric_items.c.max_score.type, Numeric)
    assert isinstance(grading_results.c.ai_score.type, Numeric)
