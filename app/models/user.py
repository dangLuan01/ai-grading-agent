from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import MYSQL_TABLE_ARGS, Base, TimestampMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.assignment import Assignment
    from app.models.grading import GradingResult


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=UserRole.TEACHER.value,
        server_default=UserRole.TEACHER.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    assignments_created: Mapped[list[Assignment]] = relationship(
        "Assignment",
        back_populates="creator",
    )
    grading_overrides: Mapped[list[GradingResult]] = relationship(
        "GradingResult",
        back_populates="teacher_override_user",
    )
