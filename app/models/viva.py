from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import MYSQL_TABLE_ARGS, Base
from app.models.enums import VivaDifficulty

if TYPE_CHECKING:
    from app.models.grading import GradingRun


class VivaQuestion(Base):
    __tablename__ = "viva_questions"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grading_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("grading_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=VivaDifficulty.MEDIUM.value,
        server_default=VivaDifficulty.MEDIUM.value,
    )
    source_file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    grading_run: Mapped[GradingRun] = relationship("GradingRun", back_populates="viva_questions")
