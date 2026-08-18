from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import MYSQL_TABLE_ARGS, Base, TimestampMixin
from app.models.enums import AssignmentStatus

if TYPE_CHECKING:
    from app.models.rubric import Rubric
    from app.models.submission import Submission
    from app.models.user import User


class Assignment(Base, TimestampMixin):
    __tablename__ = "assignments"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    total_score: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AssignmentStatus.DRAFT.value,
        server_default=AssignmentStatus.DRAFT.value,
    )
    created_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    creator: Mapped[User] = relationship("User", back_populates="assignments_created")
    rubrics: Mapped[list[Rubric]] = relationship("Rubric", back_populates="assignment")
    submissions: Mapped[list[Submission]] = relationship("Submission", back_populates="assignment")
