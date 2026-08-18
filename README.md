# AI Assignment Grading Agent

Backend service for an AI-assisted assignment grading workflow. This repository is currently implemented through **Phase 5: Batch Submission Import + GitHub Collection** from `MASTER_PROMPT.md`, adjusted for the teacher-centric V1 workflow.

## Overview

The current implementation provides the production foundation, assignment CRUD, manual and AI-generated rubric lifecycle support, a provider-independent LLM abstraction layer, and teacher-managed batch submission import from GitHub repositories.

The application connects to an **external MySQL 8.4+ server** using `DATABASE_URL`. Docker Compose does not create MySQL.

## Features

- FastAPI app with `/health`, `/ready`, `/api/v1/auth/login`, and `/api/v1/auth/me`.
- Pydantic Settings loaded from environment variables and optional `.env`.
- Production startup safety for `JWT_SECRET`.
- SQLAlchemy 2.x model foundation for the full grading domain.
- Alembic initial migration targeting MySQL with `utf8mb4`.
- JWT bearer authentication and bcrypt password hashing.
- Admin creation script without committed credentials.
- Docker Compose for the API container only.
- Assignment CRUD with safe archive delete.
- Manual teacher-provided rubric creation.
- Deterministic rubric validation for total score, duplicate/empty criteria, missing descriptions, and non-positive scores.
- Rubric draft editing, locked-rubric immutability, new draft versions after lock, and lock validation.
- LLM provider interface with Gemini, Qwen, DeepSeek, primary/fallback routing, structured-output validation, retry policy, and deterministic fake provider for tests.
- Assignment analyzer, AI rubric generator, AI rubric validator, versioned prompt files, and `POST /api/v1/assignments/{assignment_id}/rubric/generate`.
- AI-generated rubrics are persisted as `AI_GENERATED` and remain `DRAFT` until a teacher reviews and locks them.
- Teacher-provided rubrics can be checked with AI validation warnings without being modified automatically.
- Teacher-centric batch submission import from CSV, XLSX, or JSON payloads.
- Student records are created or reused by `student_code`; students do not log in or submit directly in V1.
- Public GitHub repository validation, default branch resolution, exact HEAD commit SHA snapshotting, and repository file inventory.
- Per-row import and collection status so one bad repository does not stop the batch.
- Repository limits, ignored directories, symlink skipping, and temporary workspace cleanup.
- Phase 1 through Phase 5 tests that do not require a real MySQL server, real LLM API calls, or real GitHub API calls.

## Architecture

Current deployment shape:

```text
External MySQL Server
        ^
        | DATABASE_URL
        |
FastAPI application or FastAPI Docker container
```

Code organization:

- `app/api`: HTTP routing and FastAPI dependencies.
- `app/core`: settings, security, logging, and error handling.
- `app/db`: SQLAlchemy metadata, engine, and sessions.
- `app/models`: persistent domain model foundation.
- `app/schemas`: Pydantic request and response schemas.
- `app/services`: business services, including assignment, rubric, GitHub collection, and submission import rules.
- `app/graders`: assignment analysis, AI rubric generation, AI rubric validation, and prompt-backed structured outputs.
- `app/llm`: provider-independent LLM interface, provider implementations, router, structured parsing, and fake provider.
- `prompts`: versioned prompt files used by the AI rubric workflow.
- `alembic`: database migrations.
- `scripts`: operational scripts.

Later phases will fill in parser, grading, viva, and teacher review services.

## Requirements

- Python 3.12+
- External MySQL 8.4+ database
- Docker and Docker Compose for the containerized API path

The database/schema must already exist or be creatable by the configured MySQL user before running migrations. Alembic manages application tables; it does not create or delete the external database itself.

## Setup

```bash
cp .env.example .env
```

Set `DATABASE_URL` to your external MySQL server:

```env
DATABASE_URL=mysql+pymysql://ai_grading:strong_password@192.168.1.100:3306/ai_grading?charset=utf8mb4
```

In production, set:

```env
APP_ENV=production
JWT_SECRET=<at-least-32-bytes-random-secret>
```

Production startup fails if `JWT_SECRET` is missing, still `change-me`, shorter than 32 bytes, or clearly weak.

## Environment Variables

Important variables are listed in `.env.example`, including:

- `DATABASE_URL`
- `JWT_SECRET`
- `JWT_ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `GITHUB_TOKEN`
- LLM provider settings

`DATABASE_URL` is the single source of truth for database connection information. The app does not read separate MySQL username/password/database variables.

## Local Python / External MySQL

```text
FastAPI -> External MySQL
```

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Open:

```text
http://localhost:8000/docs
```

## Docker / External MySQL

```text
FastAPI Container -> External MySQL
```

```bash
docker compose up -d --build
```

The Compose file starts only the API service. Docker Compose reads `.env` for variable interpolation and passes an explicit application variable allowlist to the container. It does not provision MySQL or create a MySQL volume.

By default, the container does not run migrations automatically. The normal production flow is:

```bash
alembic upgrade head
docker compose up -d --build
```

Optional startup migrations are available only when explicitly enabled:

```env
RUN_MIGRATIONS_ON_STARTUP=true
```

This still only runs Alembic schema migrations against `DATABASE_URL`; it does not create or delete the external database.

## Docker Networking Caveat

`DATABASE_URL` may point to hosts such as:

```text
192.168.1.100
mysql.example.internal
database.example.com
```

If MySQL runs directly on the same machine as Docker, `localhost` inside the container means the container itself, not the Docker host. On Linux, use an address reachable from the container, such as the host's LAN IP, a Docker bridge gateway address, or a host alias configured by your deployment environment.

Do not rely on a hard-coded hostname such as `db`; configure the hostname entirely through `DATABASE_URL`.

## Alembic Migration

Run migrations from an environment that can reach the external MySQL server:

```bash
alembic upgrade head
```

Inside the running API container:

```bash
docker compose exec api alembic upgrade head
```

## Health And Readiness

Liveness:

```bash
curl http://localhost:8000/health
```

Expected:

```json
{"status":"ok"}
```

Database readiness:

```bash
curl http://localhost:8000/ready
```

When MySQL is reachable:

```json
{"status":"ready","database":"ok"}
```

When MySQL is unavailable, `/ready` returns a non-2xx structured error. Neither endpoint calls an LLM provider.

## LLM Provider Setup

Supported providers in the Phase 3 abstraction layer:

- `gemini`: Gemini REST `generateContent`
- `qwen`: OpenAI-compatible chat completions
- `deepseek`: OpenAI-compatible chat completions

Configure the active providers with environment variables:

```env
LLM_PRIMARY_PROVIDER=gemini
LLM_FALLBACK_PROVIDER=qwen

GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
GEMINI_API_KEY=
GEMINI_MODEL=

QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_API_KEY=
QWEN_MODEL=

DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=
```

Model names are never hard-coded; set them through the provider-specific `*_MODEL` variables.

The router tries the primary provider first. Timeout, rate limit, connection failure, 5xx/provider error, malformed structured output, and Pydantic validation failure can trigger fallback. Non-429 HTTP 4xx provider rejections are treated as non-retryable. Structured output is parsed as JSON directly or from a simple markdown code fence, validated with the requested Pydantic model, retried once on the same provider for structured-output failures, then routed to fallback if configured.

`FakeLLMProvider` supports deterministic plain-text responses, structured JSON responses, simulated timeout/rate-limit/provider failures, malformed output, and call counting. Default tests use fakes or mocked HTTP transports and do not call real Gemini, Qwen, or DeepSeek APIs.

## AI Rubric Generation

Phase 4 uses versioned prompt files in `prompts/`:

- `assignment_analyzer_v1.txt`
- `rubric_generator_v1.txt`
- `rubric_validator_v1.txt`

Flow:

```text
Assignment title/description/total_score
        -> Assignment Analyzer
        -> AI Rubric Generator
        -> deterministic rubric validation
        -> AI rubric quality validation
        -> AI_GENERATED DRAFT rubric
```

Generate a rubric for an assignment that does not already have one:

```bash
curl -X POST http://localhost:8000/api/v1/assignments/1/rubric/generate \
  -H "Authorization: Bearer <token>"
```

The generated rubric is not locked automatically. A teacher must review it and call:

```bash
curl -X POST http://localhost:8000/api/v1/assignments/1/rubric/lock \
  -H "Authorization: Bearer <token>"
```

AI validation warnings can be requested for a teacher-provided rubric:

```bash
curl -X POST "http://localhost:8000/api/v1/assignments/1/rubric/validate?include_ai=true" \
  -H "Authorization: Bearer <token>"
```

The AI validator returns warnings only. It does not rewrite or mutate teacher-provided rubrics. Deterministic validation still checks score totals, empty or duplicate criteria, missing descriptions, and non-positive scores.

Rubric validation responses use separate validity fields:

```json
{
  "valid": true,
  "ai_valid": true,
  "errors": [],
  "warnings": [],
  "ai_prompt_version": "v1"
}
```

`valid` is deterministic structural validity. `ai_valid` is the optional AI quality assessment and is `null` when AI validation is not requested. AI validation does not replace deterministic validation.

During AI generation, deterministic validation runs before AI quality validation. Serious AI quality failures return `INVALID_RUBRIC` and do not persist the generated rubric. Non-critical AI warnings can still return a saved `AI_GENERATED` `DRAFT` rubric with warnings for teacher review.

## Batch Submission Import

V1 is teacher-centric. Students do not authenticate and do not submit repositories through a portal. A teacher imports a batch for an assignment with:

```text
student_code,student_name,repository_url
B23DCCN001,Nguyen Van A,https://github.com/user/repo1
B23DCCN002,Tran Van B,https://github.com/user/repo2
```

Supported input formats:

- CSV body with `content-type: text/csv`
- XLSX body with `content-type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- JSON body for development/testing

JSON payload shape:

```json
{
  "submissions": [
    {
      "student_code": "B23DCCN001",
      "student_name": "Nguyen Van A",
      "repository_url": "https://github.com/user/repo1"
    }
  ]
}
```

Import endpoint:

```bash
curl -X POST http://localhost:8000/api/v1/assignments/1/submissions/import \
  -H "Authorization: Bearer <token>" \
  -H "content-type: text/csv" \
  --data-binary @submissions.csv
```

Use `?dry_run=true` to validate rows without creating students, submissions, or GitHub collection calls.

Row-level validation checks required columns, GitHub URL format, duplicate student codes in the same import, duplicate repository URLs in the same import, existing assignment submissions, duplicate repository submissions for the same assignment, and student name conflicts. Invalid rows do not abort the batch.

Example response shape:

```json
{
  "total": 40,
  "valid": 38,
  "invalid": 2,
  "imported": 38,
  "failed": 0,
  "dry_run": false,
  "rows": [
    {
      "row": 2,
      "student_code": "B23DCCN001",
      "status": "INVENTORIED",
      "errors": [],
      "submission_id": 1
    }
  ]
}
```

Per-row statuses include `VALID`, `INVALID`, `INVENTORIED`, and `FAILED`. Phase 5 only inventories repository files, so successful collection ends at `INVENTORIED`. `PARSED` and `READY_FOR_GRADING` belong to Phase 6 after file content parsing succeeds.

## GitHub Collection

The GitHub collector supports public repositories only and uses `GITHUB_TOKEN` when provided. It resolves:

- repository owner/name
- default branch
- exact HEAD commit SHA
- file inventory at the stored commit SHA, including each regular file blob SHA

The collector stores repository-relative file paths, blob SHAs, size, extension, and content type only. Phase 5 does not fetch or parse file contents; parsing starts in Phase 6.

Security rules in this phase:

- no `shell=True`
- no student code execution
- no package manager commands
- no git hooks or submodules
- skip symlinks
- reject unsafe paths
- ignore configured heavy directories such as `.git`, `node_modules`, `.venv`, `dist`, and `build`
- enforce `MAX_REPOSITORY_SIZE_MB`, `MAX_FILE_SIZE_MB`, and `MAX_PARSED_FILES`
- clean `GRADING_TEMP_DIR/{submission_id}` after collection

## Create Admin

Using prompts:

```bash
python scripts/create_admin.py
```

Using environment variables:

```bash
ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD='change-this' python scripts/create_admin.py
```

Inside Docker:

```bash
docker compose exec api python scripts/create_admin.py
```

## API Overview

- `GET /health`
- `GET /ready`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/assignments`
- `GET /api/v1/assignments`
- `GET /api/v1/assignments/{assignment_id}`
- `PATCH /api/v1/assignments/{assignment_id}`
- `DELETE /api/v1/assignments/{assignment_id}`
- `POST /api/v1/assignments/{assignment_id}/rubric`
- `GET /api/v1/assignments/{assignment_id}/rubric`
- `PUT /api/v1/assignments/{assignment_id}/rubric`
- `POST /api/v1/assignments/{assignment_id}/rubric/generate`
- `POST /api/v1/assignments/{assignment_id}/rubric/validate`
- `POST /api/v1/assignments/{assignment_id}/rubric/lock`
- `POST /api/v1/assignments/{assignment_id}/submissions/import`
- `GET /api/v1/assignments/{assignment_id}/submissions`
- `GET /api/v1/submissions/{submission_id}`

Use the returned login token as:

```text
Authorization: Bearer <token>
```

## Testing

```bash
python -m pytest -q
ruff check .
docker compose config
```

Default tests use an isolated in-memory database and do not require access to a production or external MySQL server. LLM tests use `FakeLLMProvider` or mocked HTTP transports; they do not call real Gemini, Qwen, or DeepSeek APIs. GitHub collection tests use fake clients/collectors and do not call the real GitHub API.

## Security Model

- Passwords are stored only as bcrypt hashes.
- API authentication uses signed JWT bearer tokens.
- Production refuses insecure JWT secrets.
- Error responses use a consistent envelope.
- Secrets are read from environment variables and `.env` is ignored by git.
- AI-generated rubrics are deterministically validated before persistence.
- Teacher-provided rubrics are not automatically modified by AI validation.
- Student submissions are teacher-imported from class lists; students do not log in.
- GitHub repository contents are treated as untrusted data and are inventoried without execution.
- Student submissions are not executed by this phase.

## Current Limitations

- Parsing, grading, viva, and teacher review are later phases.
