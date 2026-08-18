# AI Assignment Grading Agent

Backend service for an AI-assisted assignment grading workflow. This repository is currently implemented through **Phase 3: LLM Abstraction** from `master_prompt.md`.

## Overview

The current implementation provides the production foundation, assignment CRUD, the manual rubric lifecycle, and a provider-independent LLM abstraction layer.

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
- Phase 1, Phase 2, and Phase 3 tests that do not require a real MySQL server.

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
- `app/services`: business services, including assignment and rubric lifecycle rules.
- `app/llm`: provider-independent LLM interface, provider implementations, router, structured parsing, and fake provider.
- `alembic`: database migrations.
- `scripts`: operational scripts.

Later phases will fill in AI rubric generation, submission, parser, grading, viva, and teacher review services.

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
- `POST /api/v1/assignments/{assignment_id}/rubric/validate`
- `POST /api/v1/assignments/{assignment_id}/rubric/lock`

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

Default tests use an isolated in-memory database and do not require access to a production or external MySQL server.

## Security Model

- Passwords are stored only as bcrypt hashes.
- API authentication uses signed JWT bearer tokens.
- Production refuses insecure JWT secrets.
- Error responses use a consistent envelope.
- Secrets are read from environment variables and `.env` is ignored by git.
- Student submissions are not executed by this phase.

## Current Limitations

- AI rubric generation starts in Phase 4.
- GitHub submission collection, parsing, grading, viva, and teacher review are later phases.
