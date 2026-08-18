from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_github_collector
from app.db.session import get_db
from app.models.user import User
from app.schemas.submission import SubmissionImportResponse, SubmissionRead
from app.services.github_service import GitHubRepositoryCollector
from app.services.submission_import_service import submission_import_service
from app.services.submission_service import submission_service

router = APIRouter(tags=["Submissions"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
GitHubCollectorDep = Annotated[GitHubRepositoryCollector, Depends(get_github_collector)]


@router.post(
    "/assignments/{assignment_id}/submissions/import",
    response_model=SubmissionImportResponse,
)
async def import_assignment_submissions(
    assignment_id: int,
    request: Request,
    db: DbSession,
    _current_user: CurrentUser,
    github_collector: GitHubCollectorDep,
    dry_run: bool = Query(default=False),
):
    rows = await submission_import_service.parse_request(request)
    return await submission_import_service.import_batch(
        db,
        assignment_id,
        rows,
        github_collector,
        dry_run=dry_run,
    )


@router.get(
    "/assignments/{assignment_id}/submissions",
    response_model=list[SubmissionRead],
)
async def list_assignment_submissions(
    assignment_id: int,
    db: DbSession,
    _current_user: CurrentUser,
):
    return submission_service.list_assignment_submissions(db, assignment_id)


@router.get("/submissions/{submission_id}", response_model=SubmissionRead)
async def get_submission(
    submission_id: int,
    db: DbSession,
    _current_user: CurrentUser,
):
    return submission_service.get_submission(db, submission_id)
