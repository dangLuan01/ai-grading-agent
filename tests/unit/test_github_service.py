import inspect
from dataclasses import replace

import pytest

from app.core.config import Settings
from app.core.exceptions import DomainError, ErrorCode
from app.services import github_service
from app.services.github_service import (
    GitHubRepositoryCollector,
    GitHubRepositoryMetadata,
    GitHubRepositoryRef,
    GitHubTreeItem,
    parse_github_repository_url,
)


class FakeGitHubClient:
    def __init__(
        self,
        *,
        metadata: GitHubRepositoryMetadata | None = None,
        tree: list[GitHubTreeItem] | None = None,
        commit_sha: str = "a" * 40,
        error: DomainError | None = None,
    ) -> None:
        self.metadata = metadata or GitHubRepositoryMetadata(
            owner="example",
            name="repo",
            default_branch="main",
            private=False,
            size_bytes=1024,
        )
        self.tree = tree or []
        self.commit_sha = commit_sha
        self.error = error

    async def get_repository(self, ref: GitHubRepositoryRef) -> GitHubRepositoryMetadata:
        if self.error is not None:
            raise self.error
        return replace(self.metadata, owner=ref.owner, name=ref.name)

    async def get_branch_commit_sha(
        self,
        ref: GitHubRepositoryRef,
        branch: str,
    ) -> str:
        return self.commit_sha

    async def get_tree(
        self,
        ref: GitHubRepositoryRef,
        commit_sha: str,
    ) -> list[GitHubTreeItem]:
        return self.tree


def settings_for_tmp_path(tmp_path, **overrides) -> Settings:
    values = {
        "grading_temp_dir": str(tmp_path),
        "max_repository_size_mb": 1,
        "max_file_size_mb": 1,
        "max_parsed_files": 10,
    }
    values.update(overrides)
    return Settings(**values)


def test_parse_github_repository_url_normalizes_https_repo_url() -> None:
    ref = parse_github_repository_url("https://github.com/Owner/repo.git")

    assert ref.owner == "Owner"
    assert ref.name == "repo"
    assert ref.normalized_url == "https://github.com/Owner/repo"


def test_parse_github_repository_url_rejects_malformed_url() -> None:
    with pytest.raises(DomainError) as exc_info:
        parse_github_repository_url("https://example.com/not/github")

    assert exc_info.value.code == ErrorCode.INVALID_GITHUB_URL


async def test_collector_inventories_repository_files_and_skips_ignored_paths_and_symlinks(
    tmp_path,
) -> None:
    client = FakeGitHubClient(
        tree=[
            GitHubTreeItem(
                path="README.md",
                type="blob",
                mode="100644",
                size_bytes=100,
                blob_sha="readme-sha",
            ),
            GitHubTreeItem(
                path="src/app.py",
                type="blob",
                mode="100644",
                size_bytes=200,
                blob_sha="app-sha",
            ),
            GitHubTreeItem(
                path="node_modules/pkg/index.js",
                type="blob",
                mode="100644",
                size_bytes=300,
            ),
            GitHubTreeItem(path="unsafe/link", type="blob", mode="120000", size_bytes=10),
            GitHubTreeItem(path="vendor/submodule", type="commit", mode="160000", size_bytes=0),
            GitHubTreeItem(path="../outside.txt", type="blob", mode="100644", size_bytes=1),
        ]
    )
    collector = GitHubRepositoryCollector(
        client=client,
        settings=settings_for_tmp_path(tmp_path),
    )

    snapshot = await collector.collect("https://github.com/example/repo", submission_id=123)

    assert snapshot.commit_sha == "a" * 40
    assert [file.path for file in snapshot.files] == ["README.md", "src/app.py"]
    assert [file.blob_sha for file in snapshot.files] == ["readme-sha", "app-sha"]
    assert snapshot.files[0].extension == ".md"
    assert snapshot.files[0].content_type == "text/markdown"
    assert not (tmp_path / "123").exists()


async def test_collector_rejects_private_repository(tmp_path) -> None:
    client = FakeGitHubClient(
        metadata=GitHubRepositoryMetadata(
            owner="example",
            name="repo",
            default_branch="main",
            private=True,
            size_bytes=1024,
        )
    )
    collector = GitHubRepositoryCollector(
        client=client,
        settings=settings_for_tmp_path(tmp_path),
    )

    with pytest.raises(DomainError) as exc_info:
        await collector.collect("https://github.com/example/repo", submission_id=1)

    assert exc_info.value.code == ErrorCode.REPOSITORY_PRIVATE
    assert not (tmp_path / "1").exists()


async def test_collector_propagates_repository_not_found(tmp_path) -> None:
    client = FakeGitHubClient(
        error=DomainError(ErrorCode.REPOSITORY_NOT_FOUND, "missing repository")
    )
    collector = GitHubRepositoryCollector(
        client=client,
        settings=settings_for_tmp_path(tmp_path),
    )

    with pytest.raises(DomainError) as exc_info:
        await collector.collect("https://github.com/example/missing", submission_id=1)

    assert exc_info.value.code == ErrorCode.REPOSITORY_NOT_FOUND


async def test_collector_propagates_github_rate_limit(tmp_path) -> None:
    client = FakeGitHubClient(
        error=DomainError(ErrorCode.GITHUB_RATE_LIMIT, "rate limited")
    )
    collector = GitHubRepositoryCollector(
        client=client,
        settings=settings_for_tmp_path(tmp_path),
    )

    with pytest.raises(DomainError) as exc_info:
        await collector.collect("https://github.com/example/repo", submission_id=1)

    assert exc_info.value.code == ErrorCode.GITHUB_RATE_LIMIT


async def test_collector_rejects_repository_too_large(tmp_path) -> None:
    client = FakeGitHubClient(
        metadata=GitHubRepositoryMetadata(
            owner="example",
            name="repo",
            default_branch="main",
            private=False,
            size_bytes=2 * 1024 * 1024,
        )
    )
    collector = GitHubRepositoryCollector(
        client=client,
        settings=settings_for_tmp_path(tmp_path),
    )

    with pytest.raises(DomainError) as exc_info:
        await collector.collect("https://github.com/example/repo", submission_id=1)

    assert exc_info.value.code == ErrorCode.REPOSITORY_TOO_LARGE


async def test_collector_rejects_file_too_large(tmp_path) -> None:
    client = FakeGitHubClient(
        tree=[
            GitHubTreeItem(
                path="report.pdf",
                type="blob",
                mode="100644",
                size_bytes=2 * 1024 * 1024,
                blob_sha="report-sha",
            )
        ]
    )
    collector = GitHubRepositoryCollector(
        client=client,
        settings=settings_for_tmp_path(tmp_path),
    )

    with pytest.raises(DomainError) as exc_info:
        await collector.collect("https://github.com/example/repo", submission_id=1)

    assert exc_info.value.code == ErrorCode.FILE_TOO_LARGE


async def test_collector_rejects_too_many_files(tmp_path) -> None:
    client = FakeGitHubClient(
        tree=[
            GitHubTreeItem(path="a.txt", type="blob", mode="100644", size_bytes=1),
            GitHubTreeItem(path="b.txt", type="blob", mode="100644", size_bytes=1),
            GitHubTreeItem(path="c.txt", type="blob", mode="100644", size_bytes=1),
        ]
    )
    collector = GitHubRepositoryCollector(
        client=client,
        settings=settings_for_tmp_path(tmp_path, max_parsed_files=2),
    )

    with pytest.raises(DomainError) as exc_info:
        await collector.collect("https://github.com/example/repo", submission_id=1)

    assert exc_info.value.code == ErrorCode.TOO_MANY_FILES


def test_github_service_does_not_shell_out_or_execute_student_code() -> None:
    source = inspect.getsource(github_service)

    assert "subprocess" not in source
    assert "shell=True" not in source
    assert "os.system" not in source
    assert "pip install" not in source
    assert "npm install" not in source
