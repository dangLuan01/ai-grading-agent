from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import MYSQL_TABLE_ARGS, Base
from app.models.enums import SubmissionFileParseStatus, SubmissionStatus

if TYPE_CHECKING:
    from app.models.assignment import Assignment
    from app.models.grading import GradingEvidence, GradingRun
    from app.models.rubric import Rubric
    from app.models.student import Student


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("assignments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("students.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    repository_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    repository_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    repository_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rubric_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("rubrics.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    rubric_version_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SubmissionStatus.RECEIVED.value,
        server_default=SubmissionStatus.RECEIVED.value,
    )
    submitted_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    assignment: Mapped[Assignment] = relationship("Assignment", back_populates="submissions")
    student: Mapped[Student] = relationship("Student", back_populates="submissions")
    rubric: Mapped[Rubric | None] = relationship("Rubric")
    files: Mapped[list[SubmissionFile]] = relationship(
        "SubmissionFile",
        back_populates="submission",
        cascade="all, delete-orphan",
    )
    grading_runs: Mapped[list[GradingRun]] = relationship(
        "GradingRun",
        back_populates="submission",
    )


class SubmissionFile(Base):
    __tablename__ = "submission_files"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    extension: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parse_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SubmissionFileParseStatus.PENDING.value,
        server_default=SubmissionFileParseStatus.PENDING.value,
    )
    parse_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    submission: Mapped[Submission] = relationship("Submission", back_populates="files")
    evidence_items: Mapped[list[GradingEvidence]] = relationship(
        "GradingEvidence",
        back_populates="submission_file",
    )
