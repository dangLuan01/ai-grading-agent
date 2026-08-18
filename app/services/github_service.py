from __future__ import annotations

import mimetypes
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from fastapi import status

from app.core.config import Settings, get_settings
from app.core.exceptions import DomainError, ErrorCode

IGNORE_DIRECTORIES = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    "coverage",
    ".next",
    ".idea",
    ".vscode",
    "vendor",
    "target",
    "bin",
    "obj",
}


@dataclass(frozen=True)
class GitHubRepositoryRef:
    owner: str
    name: str
    normalized_url: str


@dataclass(frozen=True)
class GitHubRepositoryMetadata:
    owner: str
    name: str
    default_branch: str
    private: bool
    size_bytes: int


@dataclass(frozen=True)
class GitHubTreeItem:
    path: str
    type: str
    mode: str
    size_bytes: int
    blob_sha: str | None = None


@dataclass(frozen=True)
class GitHubInventoryFile:
    path: str
    extension: str | None
    content_type: str | None
    size_bytes: int
    blob_sha: str | None = None


@dataclass(frozen=True)
class GitHubRepositorySnapshot:
    owner: str
    name: str
    default_branch: str
    commit_sha: str
    files: list[GitHubInventoryFile]


class GitHubClient(Protocol):
    async def get_repository(self, ref: GitHubRepositoryRef) -> GitHubRepositoryMetadata:
        raise NotImplementedError

    async def get_branch_commit_sha(
        self,
        ref: GitHubRepositoryRef,
        branch: str,
    ) -> str:
        raise NotImplementedError

    async def get_tree(
        self,
        ref: GitHubRepositoryRef,
        commit_sha: str,
    ) -> Sequence[GitHubTreeItem]:
        raise NotImplementedError


class GitHubRestClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._http_client = http_client

    async def get_repository(self, ref: GitHubRepositoryRef) -> GitHubRepositoryMetadata:
        data = await self._request_json(f"https://api.github.com/repos/{ref.owner}/{ref.name}")
        return GitHubRepositoryMetadata(
            owner=ref.owner,
            name=ref.name,
            default_branch=str(data.get("default_branch") or ""),
            private=bool(data.get("private")),
            size_bytes=int(data.get("size") or 0) * 1024,
        )

    async def get_branch_commit_sha(
        self,
        ref: GitHubRepositoryRef,
        branch: str,
    ) -> str:
        data = await self._request_json(
            f"https://api.github.com/repos/{ref.owner}/{ref.name}/branches/{branch}"
        )
        commit = data.get("commit") if isinstance(data.get("commit"), dict) else {}
        sha = commit.get("sha")
        if not isinstance(sha, str) or not sha:
            raise DomainError(
                ErrorCode.REPOSITORY_NOT_FOUND,
                "GitHub branch metadata did not include a commit SHA.",
                status_code=status.HTTP_404_NOT_FOUND,
                details={"owner": ref.owner, "repository": ref.name, "branch": branch},
            )
        return sha

    async def get_tree(
        self,
        ref: GitHubRepositoryRef,
        commit_sha: str,
    ) -> Sequence[GitHubTreeItem]:
        data = await self._request_json(
            f"https://api.github.com/repos/{ref.owner}/{ref.name}/git/trees/"
            f"{commit_sha}?recursive=1"
        )
        if data.get("truncated"):
            raise DomainError(
                ErrorCode.TOO_MANY_FILES,
                "GitHub repository tree is too large to inventory safely.",
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                details={"owner": ref.owner, "repository": ref.name},
            )
        tree = data.get("tree")
        if not isinstance(tree, list):
            raise DomainError(
                ErrorCode.REPOSITORY_NOT_FOUND,
                "GitHub repository tree could not be read.",
                status_code=status.HTTP_404_NOT_FOUND,
                details={"owner": ref.owner, "repository": ref.name},
            )
        return [
            GitHubTreeItem(
                path=str(item.get("path") or ""),
                type=str(item.get("type") or ""),
                mode=str(item.get("mode") or ""),
                size_bytes=int(item.get("size") or 0),
                blob_sha=_optional_sha(item.get("sha")),
            )
            for item in tree
            if isinstance(item, dict)
        ]

    async def _request_json(self, url: str) -> dict[str, Any]:
        client = self._http_client or httpx.AsyncClient(timeout=30)
        close_client = self._http_client is None
        try:
            response = await client.get(url, headers=self._headers())
        except httpx.RequestError as exc:
            raise DomainError(
                ErrorCode.REPOSITORY_NOT_FOUND,
                "GitHub repository could not be accessed.",
                status_code=status.HTTP_502_BAD_GATEWAY,
            ) from exc
        finally:
            if close_client:
                await client.aclose()

        if response.status_code == 404:
            raise DomainError(
                ErrorCode.REPOSITORY_NOT_FOUND,
                "GitHub repository could not be accessed.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if response.status_code in {401, 403}:
            if response.headers.get("x-ratelimit-remaining") == "0":
                raise DomainError(
                    ErrorCode.GITHUB_RATE_LIMIT,
                    "GitHub API rate limit was reached.",
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            raise DomainError(
                ErrorCode.REPOSITORY_PRIVATE,
                "GitHub repository is not publicly accessible.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if response.status_code >= 500:
            raise DomainError(
                ErrorCode.REPOSITORY_NOT_FOUND,
                "GitHub repository could not be accessed.",
                status_code=status.HTTP_502_BAD_GATEWAY,
            )
        if response.status_code >= 400:
            raise DomainError(
                ErrorCode.REPOSITORY_NOT_FOUND,
                "GitHub repository request was rejected.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        try:
            parsed = response.json()
        except ValueError as exc:
            raise DomainError(
                ErrorCode.REPOSITORY_NOT_FOUND,
                "GitHub returned an invalid response.",
                status_code=status.HTTP_502_BAD_GATEWAY,
            ) from exc
        if not isinstance(parsed, dict):
            raise DomainError(
                ErrorCode.REPOSITORY_NOT_FOUND,
                "GitHub returned an unexpected response.",
                status_code=status.HTTP_502_BAD_GATEWAY,
            )
        return parsed

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers


class GitHubRepositoryCollector:
    def __init__(
        self,
        *,
        client: GitHubClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client or GitHubRestClient(token=self._settings.github_token)
        self._temp_root = Path(self._settings.grading_temp_dir)

    async def collect(
        self,
        repository_url: str,
        *,
        submission_id: int,
        commit_sha: str | None = None,
    ) -> GitHubRepositorySnapshot:
        ref = parse_github_repository_url(repository_url)
        workspace = self._temp_root / str(submission_id)
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        try:
            metadata = await self._client.get_repository(ref)
            if metadata.private:
                raise DomainError(
                    ErrorCode.REPOSITORY_PRIVATE,
                    "GitHub repository is not publicly accessible.",
                    status_code=status.HTTP_403_FORBIDDEN,
                    details={"repository_url": ref.normalized_url},
                )
            if metadata.size_bytes > self._settings.max_repository_size_bytes:
                raise DomainError(
                    ErrorCode.REPOSITORY_TOO_LARGE,
                    "GitHub repository exceeds the configured size limit.",
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    details={
                        "repository_url": ref.normalized_url,
                        "size_bytes": metadata.size_bytes,
                        "limit_bytes": self._settings.max_repository_size_bytes,
                    },
                )
            snapshot_commit_sha = commit_sha or await self._client.get_branch_commit_sha(
                ref,
                metadata.default_branch,
            )
            tree = await self._client.get_tree(ref, snapshot_commit_sha)
            files = self._inventory(tree, repository_url=ref.normalized_url)
            return GitHubRepositorySnapshot(
                owner=metadata.owner,
                name=metadata.name,
                default_branch=metadata.default_branch,
                commit_sha=snapshot_commit_sha,
                files=files,
            )
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def _inventory(
        self,
        tree: Sequence[GitHubTreeItem],
        *,
        repository_url: str,
    ) -> list[GitHubInventoryFile]:
        files: list[GitHubInventoryFile] = []
        total_size = 0
        for item in tree:
            if item.type != "blob" or item.mode == "120000":
                continue
            if not is_safe_repository_path(item.path) or should_ignore_path(item.path):
                continue
            if item.size_bytes > self._settings.max_file_size_bytes:
                raise DomainError(
                    ErrorCode.FILE_TOO_LARGE,
                    "Repository file exceeds the configured size limit.",
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    details={
                        "repository_url": repository_url,
                        "path": item.path,
                        "size_bytes": item.size_bytes,
                        "limit_bytes": self._settings.max_file_size_bytes,
                    },
                )
            total_size += item.size_bytes
            if total_size > self._settings.max_repository_size_bytes:
                raise DomainError(
                    ErrorCode.REPOSITORY_TOO_LARGE,
                    "Repository inventory exceeds the configured size limit.",
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    details={
                        "repository_url": repository_url,
                        "size_bytes": total_size,
                        "limit_bytes": self._settings.max_repository_size_bytes,
                    },
                )
            if len(files) >= self._settings.max_parsed_files:
                raise DomainError(
                    ErrorCode.TOO_MANY_FILES,
                    "Repository contains too many inventory files.",
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    details={
                        "repository_url": repository_url,
                        "limit": self._settings.max_parsed_files,
                    },
                )
            files.append(
                GitHubInventoryFile(
                    path=item.path,
                    extension=PurePosixPath(item.path).suffix.lower() or None,
                    content_type=mimetypes.guess_type(item.path)[0],
                    size_bytes=item.size_bytes,
                    blob_sha=item.blob_sha,
                )
            )
        return files


def parse_github_repository_url(repository_url: str) -> GitHubRepositoryRef:
    parsed = urlparse(repository_url.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise DomainError(
            ErrorCode.INVALID_GITHUB_URL,
            "Repository URL must be an HTTPS GitHub repository URL.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"repository_url": repository_url},
        )
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:
        raise DomainError(
            ErrorCode.INVALID_GITHUB_URL,
            "Repository URL must identify exactly one GitHub owner and repository.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"repository_url": repository_url},
        )
    owner = parts[0].strip()
    name = parts[1].removesuffix(".git").strip()
    if not _is_valid_github_component(owner) or not _is_valid_github_component(name):
        raise DomainError(
            ErrorCode.INVALID_GITHUB_URL,
            "Repository URL contains an invalid GitHub owner or repository name.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"repository_url": repository_url},
        )
    return GitHubRepositoryRef(
        owner=owner,
        name=name,
        normalized_url=f"https://github.com/{owner}/{name}",
    )


def should_ignore_path(path: str) -> bool:
    return any(part in IGNORE_DIRECTORIES for part in PurePosixPath(path).parts)


def is_safe_repository_path(path: str) -> bool:
    if not path or path.startswith(("/", "\\")) or "\\" in path:
        return False
    parts = PurePosixPath(path).parts
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts)


def _is_valid_github_component(value: str) -> bool:
    if not value or len(value) > 100:
        return False
    return all(character.isalnum() or character in {"-", "_", "."} for character in value)


def _optional_sha(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
