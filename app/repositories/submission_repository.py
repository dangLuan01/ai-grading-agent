from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import SubmissionFileParseStatus, SubmissionStatus
from app.models.submission import Submission, SubmissionFile


class SubmissionRepository:
    def get(self, db: Session, submission_id: int) -> Submission | None:
        statement = (
            select(Submission)
            .options(selectinload(Submission.student), selectinload(Submission.files))
            .where(Submission.id == submission_id)
        )
        return db.execute(statement).scalar_one_or_none()

    def list_for_assignment(self, db: Session, assignment_id: int) -> list[Submission]:
        statement = (
            select(Submission)
            .options(selectinload(Submission.student), selectinload(Submission.files))
            .where(Submission.assignment_id == assignment_id)
            .order_by(Submission.id)
        )
        return list(db.execute(statement).scalars().all())

    def get_for_assignment_student(
        self,
        db: Session,
        *,
        assignment_id: int,
        student_id: int,
    ) -> Submission | None:
        statement = select(Submission).where(
            Submission.assignment_id == assignment_id,
            Submission.student_id == student_id,
        )
        return db.execute(statement).scalar_one_or_none()

    def get_for_assignment_repository(
        self,
        db: Session,
        *,
        assignment_id: int,
        repository_url: str,
    ) -> Submission | None:
        statement = select(Submission).where(
            Submission.assignment_id == assignment_id,
            Submission.repository_url == repository_url,
        )
        return db.execute(statement).scalar_one_or_none()

    def create(
        self,
        db: Session,
        *,
        assignment_id: int,
        student_id: int,
        repository_url: str,
        rubric_id: int | None,
        rubric_version_used: int | None,
    ) -> Submission:
        submission = Submission(
            assignment_id=assignment_id,
            student_id=student_id,
            repository_url=repository_url,
            rubric_id=rubric_id,
            rubric_version_used=rubric_version_used,
            status=SubmissionStatus.RECEIVED.value,
        )
        db.add(submission)
        db.commit()
        db.refresh(submission)
        return submission

    def set_status(
        self,
        db: Session,
        submission: Submission,
        status: SubmissionStatus,
    ) -> Submission:
        submission.status = status.value
        db.commit()
        db.refresh(submission)
        return submission

    def save_snapshot(
        self,
        db: Session,
        submission: Submission,
        *,
        repository_owner: str,
        repository_name: str,
        branch: str,
        commit_sha: str,
        files: Sequence[SubmissionFile],
    ) -> Submission:
        submission.repository_owner = repository_owner
        submission.repository_name = repository_name
        submission.branch = branch
        submission.commit_sha = commit_sha
        submission.files = list(files)
        submission.status = SubmissionStatus.INVENTORIED.value
        db.commit()
        return self.get(db, submission.id) or submission

    def build_file(
        self,
        *,
        path: str,
        blob_sha: str | None,
        extension: str | None,
        content_type: str | None,
        size_bytes: int,
    ) -> SubmissionFile:
        return SubmissionFile(
            path=path,
            blob_sha=blob_sha,
            extension=extension,
            content_type=content_type,
            size_bytes=size_bytes,
            parse_status=SubmissionFileParseStatus.PENDING.value,
        )


submission_repository = SubmissionRepository()
