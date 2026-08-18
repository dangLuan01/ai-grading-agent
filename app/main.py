from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api import assignments, auth, health, rubrics
from app.core.config import get_settings
from app.core.exceptions import (
    DomainError,
    domain_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()

    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="0.1.0",
        openapi_tags=[
            {"name": "Auth", "description": "Authentication endpoints."},
            {"name": "Assignments", "description": "Assignment management endpoints."},
            {"name": "Rubrics", "description": "Rubric lifecycle endpoints."},
            {"name": "Health", "description": "Service health endpoints."},
        ],
    )
    application.add_exception_handler(DomainError, domain_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)

    application.include_router(auth.router, prefix=settings.api_v1_prefix)
    application.include_router(assignments.router, prefix=settings.api_v1_prefix)
    application.include_router(rubrics.router, prefix=settings.api_v1_prefix)
    application.include_router(health.router)

    return application


app = create_app()
