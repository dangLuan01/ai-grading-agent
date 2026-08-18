from collections.abc import Callable
from decimal import Decimal

from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import get_llm_router_dependency, get_llm_router_factory
from app.llm.fake_provider import FakeLLMProvider
from app.llm.router import LLMRouter


def generated_ai_rubric_response() -> dict:
    return {
        "assignment_type": "requirements_analysis",
        "requirements": ["Analyze appointment scheduling requirements"],
        "rubric": [
            {
                "criterion": "Requirements coverage",
                "description": "Identifies and explains required scheduling behavior.",
                "max_score": "60",
                "evaluation_guide": {"excellent": "Complete and precise."},
                "expected_evidence": ["Functional requirements"],
            },
            {
                "criterion": "Clarity",
                "description": "Presents analysis clearly for stakeholders.",
                "max_score": "40",
                "evaluation_guide": {"excellent": "Well organized."},
                "expected_evidence": ["Structured report"],
            },
        ],
    }


def analysis_response() -> dict:
    return {
        "assignment_type": "requirements_analysis",
        "requirements": ["Analyze appointment scheduling requirements"],
        "expected_outputs": ["Requirements report"],
        "constraints": ["Submit a PDF report"],
    }


def valid_ai_quality_response(warnings: list[dict] | None = None) -> dict:
    return {"valid": True, "warnings": warnings or []}


async def create_assignment(client: AsyncClient, auth_headers: dict[str, str]) -> dict:
    response = await client.post(
        "/api/v1/assignments",
        headers=auth_headers,
        json={
            "title": "Appointment scheduling analysis",
            "description": "Analyze appointment scheduling requirements for a clinic.",
            "total_score": "100",
        },
    )
    assert response.status_code == 201
    return response.json()


def manual_rubric_payload() -> dict:
    return {
        "items": [
            {
                "criterion": "Requirements coverage",
                "description": "Identifies the required scheduling behavior.",
                "max_score": "60",
                "evaluation_guide": {},
                "expected_evidence": ["Functional requirements"],
            },
            {
                "criterion": "Clarity",
                "description": "Presents the analysis clearly.",
                "max_score": "40",
                "evaluation_guide": {},
                "expected_evidence": ["Structured report"],
            },
        ]
    }


def override_llm_router(app: FastAPI, router: LLMRouter) -> None:
    async def dependency() -> LLMRouter:
        return router

    async def factory_dependency() -> Callable[[], LLMRouter]:
        return lambda: router

    app.dependency_overrides[get_llm_router_dependency] = dependency
    app.dependency_overrides[get_llm_router_factory] = factory_dependency


async def test_generate_ai_rubric_endpoint_creates_draft_from_assignment_only(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake = FakeLLMProvider(
        responses=[
            analysis_response(),
            generated_ai_rubric_response(),
            valid_ai_quality_response(
                [
                    {
                        "code": "REVIEW_CONSTRAINT",
                        "message": "Teacher should confirm the report format evidence.",
                        "criterion": None,
                    }
                ]
            ),
        ]
    )
    override_llm_router(app, LLMRouter(primary_provider=fake))
    assignment = await create_assignment(client, auth_headers)

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric/generate",
        headers=auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    rubric = body["rubric"]
    assert rubric["source"] == "AI_GENERATED"
    assert rubric["status"] == "DRAFT"
    assert rubric["version"] == 1
    assert body["analysis"]["assignment_type"] == "requirements_analysis"
    assert body["analysis"]["constraints"] == ["Submit a PDF report"]
    assert body["ai_valid"] is True
    assert body["warnings"][0]["code"] == "REVIEW_CONSTRAINT"
    assert body["prompt_versions"] == {
        "assignment_analyzer": "v1",
        "rubric_generator": "v1",
        "rubric_validator": "v1",
    }
    assert sum(Decimal(item["max_score"]) for item in rubric["items"]) == Decimal("100.00")
    assert fake.call_count == 3
    generator_message = fake.seen_messages[1][1].content
    assert "Appointment scheduling analysis" in generator_message
    assert "Assignment total score: 100.00" in generator_message
    assert "Submit a PDF report" in generator_message
    assert "Rubric source: AI_GENERATED" in fake.seen_messages[2][1].content


async def test_generate_ai_rubric_endpoint_rejects_wrong_total(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    invalid_rubric = generated_ai_rubric_response()
    invalid_rubric["rubric"][0]["max_score"] = "50"
    fake = FakeLLMProvider(responses=[analysis_response(), invalid_rubric])
    override_llm_router(app, LLMRouter(primary_provider=fake))
    assignment = await create_assignment(client, auth_headers)

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric/generate",
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_RUBRIC"
    error_codes = {error["code"] for error in response.json()["error"]["details"]["errors"]}
    assert "TOTAL_SCORE_MISMATCH" in error_codes
    assert fake.call_count == 2


async def test_generate_ai_rubric_endpoint_rejects_serious_ai_quality_failure(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake = FakeLLMProvider(
        responses=[
            analysis_response(),
            generated_ai_rubric_response(),
            {
                "valid": False,
                "warnings": [
                    {
                        "code": "MISSING_MAJOR_REQUIREMENT",
                        "message": "The rubric misses the scheduling workflow requirement.",
                        "criterion": None,
                    }
                ],
            },
        ]
    )
    override_llm_router(app, LLMRouter(primary_provider=fake))
    assignment = await create_assignment(client, auth_headers)

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric/generate",
        headers=auth_headers,
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "INVALID_RUBRIC"
    assert body["error"]["details"]["ai_valid"] is False
    assert body["error"]["details"]["warnings"][0]["code"] == "MISSING_MAJOR_REQUIREMENT"
    assert fake.call_count == 3

    get_response = await client.get(
        f"/api/v1/assignments/{assignment['id']}/rubric",
        headers=auth_headers,
    )
    assert get_response.status_code == 404


async def test_teacher_provided_rubric_ai_validation_returns_warnings_without_changes(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    fake = FakeLLMProvider(
        responses=[
            {
                "valid": True,
                "warnings": [
                    {
                        "code": "AMBIGUOUS_CRITERION",
                        "message": "Clarify whether non-functional requirements are expected.",
                        "criterion": "Requirements coverage",
                    }
                ],
            }
        ]
    )
    override_llm_router(app, LLMRouter(primary_provider=fake))
    assignment = await create_assignment(client, auth_headers)
    create_response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric",
        headers=auth_headers,
        json=manual_rubric_payload(),
    )
    assert create_response.status_code == 201

    validate_response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric/validate?include_ai=true",
        headers=auth_headers,
    )

    assert validate_response.status_code == 200
    body = validate_response.json()
    assert body["valid"] is True
    assert body["ai_valid"] is True
    assert body["errors"] == []
    assert body["warnings"][0]["code"] == "AMBIGUOUS_CRITERION"
    assert body["ai_prompt_version"] == "v1"
    assert fake.call_count == 1

    get_response = await client.get(
        f"/api/v1/assignments/{assignment['id']}/rubric",
        headers=auth_headers,
    )
    assert get_response.status_code == 200
    latest = get_response.json()
    assert latest["source"] == "TEACHER_PROVIDED"
    assert latest["status"] == "DRAFT"
    assert latest["items"][0]["description"] == "Identifies the required scheduling behavior."
