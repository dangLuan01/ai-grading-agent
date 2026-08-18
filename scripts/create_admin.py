from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.security import hash_password  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.models.user import User  # noqa: E402


def read_value(env_name: str, prompt: str, *, secret: bool = False) -> str:
    value = os.environ.get(env_name)
    if value:
        return value
    if secret:
        return getpass.getpass(prompt)
    return input(prompt)


def main() -> int:
    email = read_value("ADMIN_EMAIL", "Admin email: ").strip().lower()
    password = read_value("ADMIN_PASSWORD", "Admin password: ", secret=True)

    if not email or not password:
        print("Admin email and password are required.", file=sys.stderr)
        return 1

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    with SessionLocal() as db:
        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing is not None:
            existing.password_hash = password_hash
            existing.role = UserRole.ADMIN.value
            existing.is_active = True
            print(f"Updated admin user: {email}")
        else:
            db.add(
                User(
                    email=email,
                    password_hash=password_hash,
                    role=UserRole.ADMIN.value,
                    is_active=True,
                )
            )
            print(f"Created admin user: {email}")
        db.commit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
