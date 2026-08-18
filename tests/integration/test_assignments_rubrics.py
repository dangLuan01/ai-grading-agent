from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models.enums import RubricSource, RubricStatus
from app.models.rubric import Rubric, RubricItem


async def create_assignment(
    client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    title: str = "System analysis",
    total_score: str = "100",
) -> dict:
    response = await client.post(
        "/api/v1/assignments",
        headers=auth_headers,
        json={
            "title": title,
            "description": "Analyze requirements for a medical appointment system.",
            "total_score": total_score,
        },
    )
    assert response.status_code == 201
    return response.json()


def valid_rubric_payload() -> dict:
    return {
        "items": [
            {
                "criterion": "Requirements coverage",
                "description": "Identifies and explains the core functional requirements.",
                "max_score": "60",
                "evaluation_guide": {"excellent": "Complete and precise."},
                "expected_evidence": ["Requirement list", "Requirement explanation"],
            },
            {
                "criterion": "Clarity and structure",
                "description": "Presents the analysis clearly and coherently.",
                "max_score": "40",
                "evaluation_guide": {"excellent": "Clear structure and terminology."},
                "expected_evidence": ["Organized sections"],
            },
        ]
    }


async def test_create_assignment(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    assignment = await create_assignment(client, auth_headers)

    assert assignment["title"] == "System analysis"
    assert Decimal(assignment["total_score"]) == Decimal("100.00")
    assert assignment["status"] == "DRAFT"


async def test_list_assignments(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    first = await create_assignment(client, auth_headers, title="First")
    second = await create_assignment(client, auth_headers, title="Second")

    response = await client.get("/api/v1/assignments", headers=auth_headers)

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert ids == [first["id"], second["id"]]


async def test_get_assignment(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    assignment = await create_assignment(client, auth_headers)

    response = await client.get(f"/api/v1/assignments/{assignment['id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == assignment["id"]


async def test_update_assignment(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    assignment = await create_assignment(client, auth_headers)

    response = await client.patch(
        f"/api/v1/assignments/{assignment['id']}",
        headers=auth_headers,
        json={"title": "Updated analysis", "status": "ACTIVE", "total_score": "120"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Updated analysis"
    assert body["status"] == "ACTIVE"
    assert Decimal(body["total_score"]) == Decimal("120.00")


async def test_archive_delete_assignment_safely(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    assignment = await create_assignment(client, auth_headers)

    delete_response = await client.delete(
        f"/api/v1/assignments/{assignment['id']}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "ARCHIVED"

    list_response = await client.get("/api/v1/assignments", headers=auth_headers)
    assert list_response.status_code == 200
    assert all(item["id"] != assignment["id"] for item in list_response.json())

    archived_response = await client.get(
        "/api/v1/assignments?include_archived=true",
        headers=auth_headers,
    )
    assert any(item["id"] == assignment["id"] for item in archived_response.json())


async def test_create_manual_rubric(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    assignment = await create_assignment(client, auth_headers)

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric",
        headers=auth_headers,
        json=valid_rubric_payload(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["assignment_id"] == assignment["id"]
    assert body["version"] == 1
    assert body["status"] == "DRAFT"
    assert body["source"] == "TEACHER_PROVIDED"
    assert len(body["items"]) == 2


async def test_reject_rubric_with_wrong_total_score(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    assignment = await create_assignment(client, auth_headers)
    payload = valid_rubric_payload()
    payload["items"][0]["max_score"] = "50"

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_RUBRIC"
    error_codes = {error["code"] for error in response.json()["error"]["details"]["errors"]}
    assert "TOTAL_SCORE_MISMATCH" in error_codes


async def test_reject_duplicate_criteria(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    assignment = await create_assignment(client, auth_headers)
    payload = valid_rubric_payload()
    payload["items"][1]["criterion"] = " requirements   coverage "

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 422
    error_codes = {error["code"] for error in response.json()["error"]["details"]["errors"]}
    assert "DUPLICATE_CRITERION" in error_codes


async def test_reject_empty_criterion(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    assignment = await create_assignment(client, auth_headers)
    payload = valid_rubric_payload()
    payload["items"][0]["criterion"] = " "

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 422
    error_codes = {error["code"] for error in response.json()["error"]["details"]["errors"]}
    assert "EMPTY_CRITERION" in error_codes


async def test_reject_missing_description(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    assignment = await create_assignment(client, auth_headers)
    payload = valid_rubric_payload()
    payload["items"][0]["description"] = " "

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 422
    error_codes = {error["code"] for error in response.json()["error"]["details"]["errors"]}
    assert "MISSING_DESCRIPTION" in error_codes


async def test_reject_zero_and_negative_max_score(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    assignment = await create_assignment(client, auth_headers)
    payload = valid_rubric_payload()
    payload["items"][0]["max_score"] = "0"
    payload["items"][1]["max_score"] = "-10"

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric",
        headers=auth_headers,
        json=payload,
    )

    assert response.status_code == 422
    error_codes = {error["code"] for error in response.json()["error"]["details"]["errors"]}
    assert "NON_POSITIVE_MAX_SCORE" in error_codes


async def test_lock_valid_rubric(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    assignment = await create_assignment(client, auth_headers)
    await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric",
        headers=auth_headers,
        json=valid_rubric_payload(),
    )

    validate_response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric/validate",
        headers=auth_headers,
    )
    assert validate_response.status_code == 200
    assert validate_response.json() == {"valid": True, "errors": []}

    lock_response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric/lock",
        headers=auth_headers,
    )

    assert lock_response.status_code == 200
    assert lock_response.json()["status"] == "LOCKED"
    assert lock_response.json()["locked_at"] is not None


async def test_reject_locking_invalid_rubric(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    assignment = await create_assignment(client, auth_headers)
    invalid_rubric = Rubric(
        assignment_id=assignment["id"],
        version=1,
        source=RubricSource.TEACHER_PROVIDED.value,
        status=RubricStatus.DRAFT.value,
    )
    invalid_rubric.items = [
        RubricItem(
            criterion="Incomplete total",
            description="This does not add up to the assignment total.",
            max_score=Decimal("30"),
            evaluation_guide={},
            expected_evidence=[],
            sort_order=0,
        )
    ]
    db_session.add(invalid_rubric)
    db_session.commit()

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric/lock",
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_RUBRIC"


async def test_create_new_rubric_version_from_locked_rubric_and_preserve_history(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    assignment = await create_assignment(client, auth_headers)
    create_response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric",
        headers=auth_headers,
        json=valid_rubric_payload(),
    )
    locked_v1 = await client.post(
        f"/api/v1/assignments/{assignment['id']}/rubric/lock",
        headers=auth_headers,
    )
    assert locked_v1.status_code == 200

    updated_payload = {
        "items": [
            {
                "criterion": "Requirements coverage",
                "description": "Updated draft wording for the next rubric version.",
                "max_score": "70",
                "evaluation_guide": {},
                "expected_evidence": [],
            },
            {
                "criterion": "Clarity and structure",
                "description": "Updated clarity expectations for the next version.",
                "max_score": "30",
                "evaluation_guide": {},
                "expected_evidence": [],
            },
        ]
    }
    update_response = await client.put(
        f"/api/v1/assignments/{assignment['id']}/rubric",
        headers=auth_headers,
        json=updated_payload,
    )

    assert update_response.status_code == 200
    body = update_response.json()
    assert body["version"] == 2
    assert body["status"] == "DRAFT"
    assert body["items"][0]["description"] == "Updated draft wording for the next rubric version."

    db_session.expire_all()
    historical = db_session.get(Rubric, create_response.json()["id"])
    assert historical is not None
    assert historical.status == "LOCKED"
    assert historical.version == 1
    assert historical.items[0].description == (
        "Identifies and explains the core functional requirements."
    )
