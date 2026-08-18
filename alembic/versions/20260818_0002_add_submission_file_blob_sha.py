"""Add blob SHA to submission file inventory.

Revision ID: 20260818_0002
Revises: 20260818_0001
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260818_0002"
down_revision: str | None = "20260818_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("submission_files", sa.Column("blob_sha", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("submission_files", "blob_sha")
