#!/usr/bin/env sh
set -eu

if [ "${RUN_MIGRATIONS_ON_STARTUP:-false}" = "true" ]; then
    python - <<'PY'
import os
import time

from sqlalchemy import create_engine, text

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL is required to run migrations on startup.")

last_error = None
for _ in range(30):
    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        last_error = None
        break
    except Exception as exc:
        last_error = exc
        time.sleep(2)
if last_error is not None:
    raise last_error
PY
    alembic upgrade head
fi

exec "$@"
