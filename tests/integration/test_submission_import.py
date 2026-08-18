from dataclasses import replace
from io import BytesIO

from fastapi import FastAPI
from httpx import AsyncClient
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_github_collector
from app.core.exceptions import DomainError, ErrorCode
from app.models.student import Student
from app.models.submission import SubmissionFile
from app.services.github_service import GitHubInventoryFile, GitHubRepositorySnapshot
from app.services.submission_service import submission_service


class FakeGitHubCollector:
    def __init__(
        self,
        outcomes: dict[str, GitHubRepositorySnapshot | DomainError] | None = None,
        *,
        default_files: list[GitHubInventoryFile] | None = None,
    ) -> None:
        self.outcomes = outcomes or {}
        self.default_files = default_files or [
            GitHubInventoryFile(
                path="README.md",
                extension=".md",
                content_type="text/markdown",
                size_bytes=100,
                blob_sha="readme-sha",
            )
        ]
        self.calls: list[tuple[str, int]] = []

    async def collect(
        self,
        repository_url: str,
        *,
        submission_id: int,
        commit_sha: str | None = None,
    ) -> GitHubRepositorySnapshot:
        self.calls.append((repository_url, submission_id))
        outcome = self.outcomes.get(repository_url)
        if isinstance(outcome, DomainError):
            raise outcome
        if outcome is not None:
            if commit_sha is not None:
                return replace(outcome, commit_sha=commit_sha)
            return outcome
        owner, name = repository_url.removeprefix("https://github.com/").split("/", maxsplit=1)
        return GitHubRepositorySnapshot(
            owner=owner,
            name=name,
            default_branch="main",
            commit_sha=commit_sha or "f" * 40,
            files=self.default_files,
        )


def override_github_collector(app: FastAPI, collector: FakeGitHubCollector) -> None:
    async def dependency() -> FakeGitHubCollector:
        return collector

    app.dependency_overrides[get_github_collector] = dependency


async def create_assignment(
    client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    total_score: str = "100",
) -> dict:
    response = await client.post(
        "/api/v1/assignments",
        headers=auth_headers,
        json={
            "title": "Submission import assignment",
            "description": "Import public GitHub repositories for grading.",
            "total_score": total_score,
        },
    )
    assert response.status_code == 201
    return response.json()


async def create_locked_rubric(
    client: AsyncClient,
    auth_headers: dict[str, str],
    assignment_id: int,
) -> dict:
    rubric_response = await client.post(
        f"/api/v1/assignments/{assignment_id}/rubric",
        headers=auth_headers,
        json={
            "items": [
                {
                    "criterion": "Repository completeness",
                    "description": "Contains the required deliverables.",
                    "max_score": "100",
                    "evaluation_guide": {},
                    "expected_evidence": ["Repository files"],
                }
            ]
        },
    )
    assert rubric_response.status_code == 201
    lock_response = await client.post(
        f"/api/v1/assignments/{assignment_id}/rubric/lock",
        headers=auth_headers,
    )
    assert lock_response.status_code == 200
    return lock_response.json()


async def create_assignment_with_locked_rubric(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> tuple[dict, dict]:
    assignment = await create_assignment(client, auth_headers)
    rubric = await create_locked_rubric(client, auth_headers, assignment["id"])
    return assignment, rubric


def csv_payload(*rows: tuple[str, str, str]) -> str:
    lines = ["student_code,student_name,repository_url"]
    lines.extend(",".join(row) for row in rows)
    return "\n".join(lines)


def xlsx_payload(*rows: tuple[str, str, str]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["student_code", "student_name", "repository_url"])
    for row in rows:
        sheet.append(list(row))
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


async def test_csv_import_collects_commit_inventory_and_binds_locked_rubric(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    collector = FakeGitHubCollector(
        default_files=[
            GitHubInventoryFile("README.md", ".md", "text/markdown", 100, "readme-sha"),
            GitHubInventoryFile("src/app.py", ".py", "text/x-python", 200, "app-sha"),
        ]
    )
    override_github_collector(app, collector)
    assignment, rubric = await create_assignment_with_locked_rubric(client, auth_headers)

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import",
        headers={**auth_headers, "content-type": "text/csv"},
        content=csv_payload(
            ("B23DCCN001", "Nguyen Van A", "https://github.com/user/repo1"),
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["valid"] == 1
    assert body["invalid"] == 0
    row = body["rows"][0]
    assert row["row"] == 2
    assert row["status"] == "INVENTORIED"
    assert row["status"] not in {"PARSED", "READY_FOR_GRADING"}
    assert row["submission_id"] is not None

    get_response = await client.get(
        f"/api/v1/submissions/{row['submission_id']}",
        headers=auth_headers,
    )
    submission = get_response.json()
    assert submission["commit_sha"] == "f" * 40
    assert submission["rubric_id"] == rubric["id"]
    assert submission["rubric_version_used"] == rubric["version"]
    assert submission["status"] == "INVENTORIED"
    assert submission["status"] not in {"PARSED", "READY_FOR_GRADING"}
    assert [file["path"] for file in submission["files"]] == ["README.md", "src/app.py"]
    assert [file["blob_sha"] for file in submission["files"]] == ["readme-sha", "app-sha"]


async def test_xlsx_import(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    collector = FakeGitHubCollector()
    override_github_collector(app, collector)
    assignment, _rubric = await create_assignment_with_locked_rubric(client, auth_headers)

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import",
        headers={
            **auth_headers,
            "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
        content=xlsx_payload(
            ("B23DCCN002", "Tran Van B", "https://github.com/user/repo2"),
        ),
    )

    assert response.status_code == 200
    assert response.json()["rows"][0]["status"] == "INVENTORIED"
    assert collector.calls == [("https://github.com/user/repo2", 1)]


async def test_json_batch_import(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    collector = FakeGitHubCollector()
    override_github_collector(app, collector)
    assignment, _rubric = await create_assignment_with_locked_rubric(client, auth_headers)

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import",
        headers=auth_headers,
        json={
            "submissions": [
                {
                    "student_code": "B23DCCN003",
                    "student_name": "Le Van C",
                    "repository_url": "https://github.com/user/repo3",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["imported"] == 1
    assert response.json()["rows"][0]["status"] == "INVENTORIED"


async def test_valid_40_row_style_batch(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    collector = FakeGitHubCollector()
    override_github_collector(app, collector)
    assignment, _rubric = await create_assignment_with_locked_rubric(client, auth_headers)
    rows = [
        {
            "student_code": f"B23DCCN{index:03d}",
            "student_name": f"Student {index}",
            "repository_url": f"https://github.com/user/repo{index}",
        }
        for index in range(1, 41)
    ]

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import",
        headers=auth_headers,
        json={"submissions": rows},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 40
    assert body["imported"] == 40
    assert body["invalid"] == 0
    assert all(row["status"] == "INVENTORIED" for row in body["rows"])
    assert len(collector.calls) == 40


async def test_partially_invalid_batch_and_duplicate_student_code(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    collector = FakeGitHubCollector()
    override_github_collector(app, collector)
    assignment, _rubric = await create_assignment_with_locked_rubric(client, auth_headers)

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import",
        headers=auth_headers,
        json={
            "submissions": [
                {
                    "student_code": "B23DCCN010",
                    "student_name": "Valid Student",
                    "repository_url": "https://github.com/user/valid",
                },
                {
                    "student_code": "",
                    "student_name": "Missing Code",
                    "repository_url": "https://github.com/user/missing-code",
                },
                {
                    "student_code": "B23DCCN011",
                    "student_name": "Bad URL",
                    "repository_url": "https://example.com/not-github",
                },
                {
                    "student_code": "B23DCCN010",
                    "student_name": "Duplicate Student",
                    "repository_url": "https://github.com/user/duplicate",
                },
            ]
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 4
    assert body["imported"] == 1
    assert body["invalid"] == 3
    assert body["rows"][0]["status"] == "INVENTORIED"
    assert "MISSING_STUDENT_CODE" in body["rows"][1]["errors"]
    assert "INVALID_GITHUB_URL" in body["rows"][2]["errors"]
    assert "DUPLICATE_STUDENT_CODE" in body["rows"][3]["errors"]
    assert len(collector.calls) == 1


async def test_dry_run_validates_without_persisting_or_collecting(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    collector = FakeGitHubCollector()
    override_github_collector(app, collector)
    assignment, _rubric = await create_assignment_with_locked_rubric(client, auth_headers)

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import?dry_run=true",
        headers=auth_headers,
        json={
            "submissions": [
                {
                    "student_code": "B23DCCN020",
                    "student_name": "Preview Student",
                    "repository_url": "https://github.com/user/preview",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["rows"][0]["status"] == "VALID"
    assert response.json()["imported"] == 0
    assert collector.calls == []


async def test_reuse_existing_student_without_duplicate(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    existing = Student(student_code="B23DCCN030", full_name="Existing Student")
    db_session.add(existing)
    db_session.commit()
    collector = FakeGitHubCollector()
    override_github_collector(app, collector)
    assignment, _rubric = await create_assignment_with_locked_rubric(client, auth_headers)

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import",
        headers=auth_headers,
        json={
            "submissions": [
                {
                    "student_code": "B23DCCN030",
                    "student_name": "Existing Student",
                    "repository_url": "https://github.com/user/reuse",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["imported"] == 1
    assert db_session.scalar(select(func.count()).select_from(Student)) == 1


async def test_student_name_conflict_is_rejected_explicitly(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    existing = Student(student_code="B23DCCN031", full_name="Correct Name")
    db_session.add(existing)
    db_session.commit()
    collector = FakeGitHubCollector()
    override_github_collector(app, collector)
    assignment, _rubric = await create_assignment_with_locked_rubric(client, auth_headers)

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import",
        headers=auth_headers,
        json={
            "submissions": [
                {
                    "student_code": "B23DCCN031",
                    "student_name": "Different Name",
                    "repository_url": "https://github.com/user/name-conflict",
                }
            ]
        },
    )

    row = response.json()["rows"][0]
    assert response.status_code == 200
    assert row["status"] == "INVALID"
    assert row["errors"] == ["STUDENT_NAME_CONFLICT"]
    assert collector.calls == []


async def test_repository_failures_are_per_student_and_do_not_abort_batch(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    collector = FakeGitHubCollector(
        outcomes={
            "https://github.com/user/not-found": DomainError(
                ErrorCode.REPOSITORY_NOT_FOUND,
                "missing repository",
            ),
            "https://github.com/user/private": DomainError(
                ErrorCode.REPOSITORY_PRIVATE,
                "private repository",
            ),
            "https://github.com/user/rate-limit": DomainError(
                ErrorCode.GITHUB_RATE_LIMIT,
                "rate limited",
            ),
        }
    )
    override_github_collector(app, collector)
    assignment, _rubric = await create_assignment_with_locked_rubric(client, auth_headers)

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import",
        headers=auth_headers,
        json={
            "submissions": [
                {
                    "student_code": "B23DCCN041",
                    "student_name": "Missing Repo",
                    "repository_url": "https://github.com/user/not-found",
                },
                {
                    "student_code": "B23DCCN042",
                    "student_name": "Private Repo",
                    "repository_url": "https://github.com/user/private",
                },
                {
                    "student_code": "B23DCCN043",
                    "student_name": "Rate Limited Repo",
                    "repository_url": "https://github.com/user/rate-limit",
                },
                {
                    "student_code": "B23DCCN044",
                    "student_name": "Good Repo",
                    "repository_url": "https://github.com/user/good",
                },
            ]
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["imported"] == 4
    assert body["failed"] == 3
    assert body["rows"][0]["errors"] == ["REPOSITORY_NOT_FOUND"]
    assert body["rows"][1]["errors"] == ["REPOSITORY_PRIVATE"]
    assert body["rows"][2]["errors"] == ["GITHUB_RATE_LIMIT"]
    assert body["rows"][3]["status"] == "INVENTORIED"
    assert len(collector.calls) == 4


async def test_submission_without_locked_rubric_is_inventoried_but_not_ready(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    collector = FakeGitHubCollector()
    override_github_collector(app, collector)
    assignment = await create_assignment(client, auth_headers)

    response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import",
        headers=auth_headers,
        json={
            "submissions": [
                {
                    "student_code": "B23DCCN050",
                    "student_name": "No Rubric Student",
                    "repository_url": "https://github.com/user/no-rubric",
                }
            ]
        },
    )

    row = response.json()["rows"][0]
    assert response.status_code == 200
    assert row["status"] == "INVENTORIED"

    submission_response = await client.get(
        f"/api/v1/submissions/{row['submission_id']}",
        headers=auth_headers,
    )
    submission = submission_response.json()
    assert submission["status"] == "INVENTORIED"
    assert submission["rubric_id"] is None
    assert submission["rubric_version_used"] is None


async def test_list_and_get_submission_endpoints(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    collector = FakeGitHubCollector()
    override_github_collector(app, collector)
    assignment, _rubric = await create_assignment_with_locked_rubric(client, auth_headers)
    import_response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import",
        headers=auth_headers,
        json={
            "submissions": [
                {
                    "student_code": "B23DCCN060",
                    "student_name": "Listed Student",
                    "repository_url": "https://github.com/user/listed",
                }
            ]
        },
    )
    submission_id = import_response.json()["rows"][0]["submission_id"]

    list_response = await client.get(
        f"/api/v1/assignments/{assignment['id']}/submissions",
        headers=auth_headers,
    )
    get_response = await client.get(f"/api/v1/submissions/{submission_id}", headers=auth_headers)

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["student"]["student_code"] == "B23DCCN060"
    assert get_response.status_code == 200
    assert get_response.json()["id"] == submission_id


async def test_duplicate_existing_repository_submission_is_rejected(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    collector = FakeGitHubCollector()
    override_github_collector(app, collector)
    assignment, _rubric = await create_assignment_with_locked_rubric(client, auth_headers)
    first_response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import",
        headers=auth_headers,
        json={
            "submissions": [
                {
                    "student_code": "B23DCCN070",
                    "student_name": "First Student",
                    "repository_url": "https://github.com/user/shared",
                }
            ]
        },
    )
    assert first_response.json()["imported"] == 1

    second_response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import",
        headers=auth_headers,
        json={
            "submissions": [
                {
                    "student_code": "B23DCCN071",
                    "student_name": "Second Student",
                    "repository_url": "https://github.com/user/shared",
                }
            ]
        },
    )

    row = second_response.json()["rows"][0]
    assert second_response.status_code == 200
    assert row["status"] == "INVALID"
    assert row["errors"] == ["DUPLICATE_REPOSITORY_SUBMISSION"]


async def test_retry_collection_replaces_inventory_without_duplicate_files(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    initial_collector = FakeGitHubCollector()
    override_github_collector(app, initial_collector)
    assignment, _rubric = await create_assignment_with_locked_rubric(client, auth_headers)
    import_response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import",
        headers=auth_headers,
        json={
            "submissions": [
                {
                    "student_code": "B23DCCN080",
                    "student_name": "Retry Student",
                    "repository_url": "https://github.com/user/retry",
                }
            ]
        },
    )
    submission_id = import_response.json()["rows"][0]["submission_id"]
    retry_collector = FakeGitHubCollector(
        default_files=[
            GitHubInventoryFile("README.md", ".md", "text/markdown", 100, "readme-sha"),
            GitHubInventoryFile("src/app.py", ".py", "text/x-python", 200, "app-sha"),
        ]
    )

    await submission_service.collect_submission(db_session, submission_id, retry_collector)
    await submission_service.collect_submission(db_session, submission_id, retry_collector)

    db_session.expire_all()
    file_count = db_session.scalar(
        select(func.count())
        .select_from(SubmissionFile)
        .where(SubmissionFile.submission_id == submission_id)
    )
    assert file_count == 2


async def test_retry_collection_preserves_existing_snapshot_commit_sha(
    app: FastAPI,
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    initial_collector = FakeGitHubCollector()
    override_github_collector(app, initial_collector)
    assignment, _rubric = await create_assignment_with_locked_rubric(client, auth_headers)
    import_response = await client.post(
        f"/api/v1/assignments/{assignment['id']}/submissions/import",
        headers=auth_headers,
        json={
            "submissions": [
                {
                    "student_code": "B23DCCN081",
                    "student_name": "Snapshot Student",
                    "repository_url": "https://github.com/user/snapshot",
                }
            ]
        },
    )
    submission_id = import_response.json()["rows"][0]["submission_id"]
    retry_collector = FakeGitHubCollector(
        outcomes={
            "https://github.com/user/snapshot": GitHubRepositorySnapshot(
                owner="user",
                name="snapshot",
                default_branch="main",
                commit_sha="b" * 40,
                files=[
                    GitHubInventoryFile(
                        path="README.md",
                        extension=".md",
                        content_type="text/markdown",
                        size_bytes=100,
                        blob_sha="new-readme-sha",
                    )
                ],
            )
        }
    )

    await submission_service.collect_submission(db_session, submission_id, retry_collector)

    submission = await client.get(f"/api/v1/submissions/{submission_id}", headers=auth_headers)
    assert submission.json()["commit_sha"] == "f" * 40
