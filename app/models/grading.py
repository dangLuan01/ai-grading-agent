from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import MYSQL_TABLE_ARGS, Base, TimestampMixin
from app.models.enums import GradingRunStatus, ReviewStatus

if TYPE_CHECKING:
    from app.models.rubric import RubricItem
    from app.models.submission import Submission, SubmissionFile
    from app.models.user import User
    from app.models.viva import VivaQuestion


class GradingRun(Base):
    __tablename__ = "grading_runs"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("submissions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=GradingRunStatus.PENDING.value,
        server_default=GradingRunStatus.PENDING.value,
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    submission: Mapped[Submission] = relationship("Submission", back_populates="grading_runs")
    results: Mapped[list[GradingResult]] = relationship(
        "GradingResult",
        back_populates="grading_run",
        cascade="all, delete-orphan",
    )
    viva_questions: Mapped[list[VivaQuestion]] = relationship(
        "VivaQuestion",
        back_populates="grading_run",
        cascade="all, delete-orphan",
    )


class GradingResult(Base, TimestampMixin):
    __tablename__ = "grading_results"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grading_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("grading_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rubric_item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("rubric_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    ai_score: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    teacher_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    issues: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ReviewStatus.NEEDS_TEACHER_REVIEW.value,
        server_default=ReviewStatus.NEEDS_TEACHER_REVIEW.value,
    )
    teacher_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    teacher_override_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    teacher_override_at: Mapped[datetime | None] = mapped_column(nullable=True)

    grading_run: Mapped[GradingRun] = relationship("GradingRun", back_populates="results")
    rubric_item: Mapped[RubricItem] = relationship("RubricItem", back_populates="grading_results")
    evidence: Mapped[list[GradingEvidence]] = relationship(
        "GradingEvidence",
        back_populates="grading_result",
        cascade="all, delete-orphan",
    )
    teacher_override_user: Mapped[User | None] = relationship(
        "User",
        back_populates="grading_overrides",
    )


class GradingEvidence(Base):
    __tablename__ = "grading_evidence"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grading_result_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("grading_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submission_file_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("submission_files.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    grading_result: Mapped[GradingResult] = relationship(
        "GradingResult",
        back_populates="evidence",
    )
    submission_file: Mapped[SubmissionFile] = relationship(
        "SubmissionFile",
        back_populates="evidence_items",
    )
