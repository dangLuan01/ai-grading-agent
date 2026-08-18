from fastapi import status
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError, ErrorCode
from app.models.enums import SubmissionStatus
from app.models.submission import Submission
from app.repositories.submission_repository import submission_repository
from app.services.assignment_service import assignment_service
from app.services.github_service import GitHubRepositoryCollector


class SubmissionService:
    def list_assignment_submissions(
        self,
        db: Session,
        assignment_id: int,
    ) -> list[Submission]:
        assignment_service.get_assignment(db, assignment_id)
        return submission_repository.list_for_assignment(db, assignment_id)

    def get_submission(self, db: Session, submission_id: int) -> Submission:
        submission = submission_repository.get(db, submission_id)
        if submission is None:
            raise DomainError(
                ErrorCode.NOT_FOUND,
                "Submission was not found.",
                status_code=status.HTTP_404_NOT_FOUND,
                details={"submission_id": submission_id},
            )
        return submission

    async def collect_submission(
        self,
        db: Session,
        submission_id: int,
        collector: GitHubRepositoryCollector,
    ) -> Submission:
        submission = self.get_submission(db, submission_id)
        submission_repository.set_status(db, submission, SubmissionStatus.COLLECTING)
        try:
            snapshot = await collector.collect(
                submission.repository_url,
                submission_id=submission.id,
                commit_sha=submission.commit_sha,
            )
        except DomainError:
            submission_repository.set_status(db, submission, SubmissionStatus.FAILED)
            raise

        files = [
            submission_repository.build_file(
                path=file.path,
                blob_sha=file.blob_sha,
                extension=file.extension,
                content_type=file.content_type,
                size_bytes=file.size_bytes,
            )
            for file in snapshot.files
        ]
        return submission_repository.save_snapshot(
            db,
            submission,
            repository_owner=snapshot.owner,
            repository_name=snapshot.name,
            branch=snapshot.default_branch,
            commit_sha=snapshot.commit_sha,
            files=files,
        )


submission_service = SubmissionService()
