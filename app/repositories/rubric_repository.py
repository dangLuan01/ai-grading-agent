from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import RubricStatus
from app.models.rubric import Rubric, RubricItem
from app.schemas.rubric import RubricItemCreate


class RubricRepository:
    def get_by_id(self, db: Session, rubric_id: int) -> Rubric | None:
        statement = (
            select(Rubric)
            .options(selectinload(Rubric.items))
            .where(Rubric.id == rubric_id)
        )
        return db.execute(statement).scalar_one_or_none()

    def get_latest_for_assignment(self, db: Session, assignment_id: int) -> Rubric | None:
        statement = (
            select(Rubric)
            .options(selectinload(Rubric.items))
            .where(
                Rubric.assignment_id == assignment_id,
                Rubric.status != RubricStatus.ARCHIVED.value,
            )
            .order_by(Rubric.version.desc())
            .limit(1)
        )
        return db.execute(statement).scalar_one_or_none()

    def next_version(self, db: Session, assignment_id: int) -> int:
        current = db.scalar(
            select(func.max(Rubric.version)).where(Rubric.assignment_id == assignment_id)
        )
        return int(current or 0) + 1

    def create(
        self,
        db: Session,
        *,
        assignment_id: int,
        version: int,
        source: str,
        items: Sequence[RubricItemCreate],
    ) -> Rubric:
        rubric = Rubric(
            assignment_id=assignment_id,
            version=version,
            source=source,
            status=RubricStatus.DRAFT.value,
        )
        rubric.items = [
            RubricItem(
                criterion=item.criterion.strip(),
                description=item.description.strip(),
                max_score=item.max_score,
                evaluation_guide=item.evaluation_guide,
                expected_evidence=item.expected_evidence,
                sort_order=index,
            )
            for index, item in enumerate(items)
        ]
        db.add(rubric)
        db.commit()
        return self.get_by_id(db, rubric.id) or rubric

    def replace_items(
        self,
        db: Session,
        rubric: Rubric,
        items: Sequence[RubricItemCreate],
        *,
        source: str | None = None,
    ) -> Rubric:
        rubric.items = [
            RubricItem(
                criterion=item.criterion.strip(),
                description=item.description.strip(),
                max_score=item.max_score,
                evaluation_guide=item.evaluation_guide,
                expected_evidence=item.expected_evidence,
                sort_order=index,
            )
            for index, item in enumerate(items)
        ]
        if source is not None:
            rubric.source = source
        db.commit()
        return self.get_by_id(db, rubric.id) or rubric

    def lock(self, db: Session, rubric: Rubric) -> Rubric:
        from datetime import UTC, datetime

        rubric.status = RubricStatus.LOCKED.value
        rubric.locked_at = datetime.now(UTC)
        db.commit()
        return self.get_by_id(db, rubric.id) or rubric


rubric_repository = RubricRepository()
