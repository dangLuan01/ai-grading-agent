from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import MYSQL_TABLE_ARGS, Base, TimestampMixin
from app.models.enums import RubricSource, RubricStatus

if TYPE_CHECKING:
    from app.models.assignment import Assignment
    from app.models.grading import GradingResult


class Rubric(Base, TimestampMixin):
    __tablename__ = "rubrics"
    __table_args__ = (
        UniqueConstraint("assignment_id", "version", name="uq_rubrics_assignment_id_version"),
        MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("assignments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=RubricSource.TEACHER_PROVIDED.value,
        server_default=RubricSource.TEACHER_PROVIDED.value,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RubricStatus.DRAFT.value,
        server_default=RubricStatus.DRAFT.value,
    )
    locked_at: Mapped[datetime | None] = mapped_column(nullable=True)

    assignment: Mapped[Assignment] = relationship("Assignment", back_populates="rubrics")
    items: Mapped[list[RubricItem]] = relationship(
        "RubricItem",
        back_populates="rubric",
        cascade="all, delete-orphan",
        order_by="RubricItem.sort_order",
    )


class RubricItem(Base):
    __tablename__ = "rubric_items"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rubric_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("rubrics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    criterion: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    max_score: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    evaluation_guide: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    expected_evidence: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    rubric: Mapped[Rubric] = relationship("Rubric", back_populates="items")
    grading_results: Mapped[list[GradingResult]] = relationship(
        "GradingResult",
        back_populates="rubric_item",
    )
