from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    LLMRouterFactory,
    get_current_user,
    get_llm_router_dependency,
    get_llm_router_factory,
)
from app.db.session import get_db
from app.llm.router import LLMRouter
from app.models.user import User
from app.schemas.rubric import (
    AssignmentAnalysisRead,
    RubricCreate,
    RubricGenerateResponse,
    RubricRead,
    RubricUpdate,
    RubricValidationIssue,
    RubricValidationResponse,
    RubricValidationWarning,
)
from app.services.ai_rubric_service import ai_rubric_service
from app.services.rubric_service import rubric_service

router = APIRouter(prefix="/assignments/{assignment_id}/rubric", tags=["Rubrics"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
LLMRouterDep = Annotated[LLMRouter, Depends(get_llm_router_dependency)]
LLMRouterFactoryDep = Annotated[LLMRouterFactory, Depends(get_llm_router_factory)]


@router.post("", response_model=RubricRead, status_code=status.HTTP_201_CREATED)
async def create_manual_rubric(
    assignment_id: int,
    payload: RubricCreate,
    db: DbSession,
    _current_user: CurrentUser,
):
    return rubric_service.create_manual_rubric(db, assignment_id, payload)


@router.get("", response_model=RubricRead)
async def get_latest_rubric(
    assignment_id: int,
    db: DbSession,
    _current_user: CurrentUser,
):
    return rubric_service.get_latest_rubric(db, assignment_id)


@router.put("", response_model=RubricRead)
async def update_latest_rubric(
    assignment_id: int,
    payload: RubricUpdate,
    db: DbSession,
    _current_user: CurrentUser,
):
    return rubric_service.update_latest_rubric(db, assignment_id, payload)


@router.post(
    "/generate",
    response_model=RubricGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_ai_rubric(
    assignment_id: int,
    db: DbSession,
    _current_user: CurrentUser,
    llm_router: LLMRouterDep,
):
    result = await ai_rubric_service.generate_rubric(db, assignment_id, llm_router)
    return RubricGenerateResponse(
        rubric=result.rubric,
        analysis=AssignmentAnalysisRead(**result.analysis.model_dump()),
        ai_valid=result.ai_validation.valid,
        warnings=[
            RubricValidationWarning(**warning.model_dump())
            for warning in result.ai_validation.warnings
        ],
        prompt_versions=result.prompt_versions,
    )


@router.post("/validate", response_model=RubricValidationResponse)
async def validate_latest_rubric(
    assignment_id: int,
    db: DbSession,
    _current_user: CurrentUser,
    llm_router_factory: LLMRouterFactoryDep,
    include_ai: bool = Query(
        default=False,
        description=(
            "When true, add LLM-generated rubric quality warnings after "
            "deterministic validation."
        ),
    ),
):
    errors = rubric_service.validate_latest_rubric(db, assignment_id)
    ai_valid = None
    warnings: list[RubricValidationWarning] = []
    ai_prompt_version = None
    if include_ai and not errors:
        llm_router = llm_router_factory()
        ai_result = await ai_rubric_service.validate_latest_rubric(
            db,
            assignment_id,
            llm_router,
        )
        warnings = [
            RubricValidationWarning(**warning.model_dump())
            for warning in ai_result.output.warnings
        ]
        ai_valid = ai_result.output.valid
        ai_prompt_version = ai_result.prompt_version
    return RubricValidationResponse(
        valid=not errors,
        ai_valid=ai_valid,
        errors=[RubricValidationIssue(**error.as_dict()) for error in errors],
        warnings=warnings,
        ai_prompt_version=ai_prompt_version,
    )


@router.post("/lock", response_model=RubricRead)
async def lock_latest_rubric(
    assignment_id: int,
    db: DbSession,
    _current_user: CurrentUser,
):
    return rubric_service.lock_latest_rubric(db, assignment_id)
