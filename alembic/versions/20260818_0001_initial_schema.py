"""Initial schema for Phase 1 foundation.

Revision ID: 20260818_0001
Revises:
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260818_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    table_options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="TEACHER", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        **table_options,
    )

    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("total_score", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="DRAFT", nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_assignments_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignments")),
        **table_options,
    )
    op.create_index(op.f("ix_assignments_created_by"), "assignments", ["created_by"], unique=False)

    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_code", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_students")),
        sa.UniqueConstraint("student_code", name=op.f("uq_students_student_code")),
        **table_options,
    )

    op.create_table(
        "rubrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "source",
            sa.String(length=64),
            server_default="TEACHER_PROVIDED",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), server_default="DRAFT", nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name=op.f("fk_rubrics_assignment_id_assignments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubrics")),
        sa.UniqueConstraint(
            "assignment_id",
            "version",
            name="uq_rubrics_assignment_id_version",
        ),
        **table_options,
    )
    op.create_index(op.f("ix_rubrics_assignment_id"), "rubrics", ["assignment_id"], unique=False)

    op.create_table(
        "rubric_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rubric_id", sa.Integer(), nullable=False),
        sa.Column("criterion", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("max_score", sa.Numeric(10, 2), nullable=False),
        sa.Column("evaluation_guide", sa.JSON(), nullable=False),
        sa.Column("expected_evidence", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["rubric_id"],
            ["rubrics.id"],
            name=op.f("fk_rubric_items_rubric_id_rubrics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubric_items")),
        **table_options,
    )
    op.create_index(op.f("ix_rubric_items_rubric_id"), "rubric_items", ["rubric_id"], unique=False)

    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("repository_url", sa.String(length=2048), nullable=False),
        sa.Column("repository_owner", sa.String(length=255), nullable=True),
        sa.Column("repository_name", sa.String(length=255), nullable=True),
        sa.Column("branch", sa.String(length=255), nullable=True),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("rubric_id", sa.Integer(), nullable=True),
        sa.Column("rubric_version_used", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="RECEIVED", nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name=op.f("fk_submissions_assignment_id_assignments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rubric_id"],
            ["rubrics.id"],
            name=op.f("fk_submissions_rubric_id_rubrics"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            name=op.f("fk_submissions_student_id_students"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
        **table_options,
    )
    op.create_index(
        op.f("ix_submissions_assignment_id"),
        "submissions",
        ["assignment_id"],
        unique=False,
    )
    op.create_index(op.f("ix_submissions_rubric_id"), "submissions", ["rubric_id"], unique=False)
    op.create_index(op.f("ix_submissions_student_id"), "submissions", ["student_id"], unique=False)

    op.create_table(
        "submission_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("extension", sa.String(length=32), nullable=True),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("parse_status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("parse_error", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_submission_files_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission_files")),
        **table_options,
    )
    op.create_index(
        op.f("ix_submission_files_submission_id"),
        "submission_files",
        ["submission_id"],
        unique=False,
    )

    op.create_table(
        "grading_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("attempt_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_grading_runs_submission_id_submissions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grading_runs")),
        **table_options,
    )
    op.create_index(
        op.f("ix_grading_runs_submission_id"),
        "grading_runs",
        ["submission_id"],
        unique=False,
    )

    op.create_table(
        "grading_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("grading_run_id", sa.Integer(), nullable=False),
        sa.Column("rubric_item_id", sa.Integer(), nullable=False),
        sa.Column("ai_score", sa.Numeric(10, 2), nullable=False),
        sa.Column("teacher_score", sa.Numeric(10, 2), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column(
            "review_status",
            sa.String(length=32),
            server_default="NEEDS_TEACHER_REVIEW",
            nullable=False,
        ),
        sa.Column("teacher_override_reason", sa.Text(), nullable=True),
        sa.Column("teacher_override_by", sa.Integer(), nullable=True),
        sa.Column("teacher_override_at", sa.DateTime(timezone=True), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["grading_run_id"],
            ["grading_runs.id"],
            name=op.f("fk_grading_results_grading_run_id_grading_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rubric_item_id"],
            ["rubric_items.id"],
            name=op.f("fk_grading_results_rubric_item_id_rubric_items"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_override_by"],
            ["users.id"],
            name=op.f("fk_grading_results_teacher_override_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grading_results")),
        **table_options,
    )
    op.create_index(
        op.f("ix_grading_results_grading_run_id"),
        "grading_results",
        ["grading_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grading_results_rubric_item_id"),
        "grading_results",
        ["rubric_item_id"],
        unique=False,
    )

    op.create_table(
        "grading_evidence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("grading_result_id", sa.Integer(), nullable=False),
        sa.Column("submission_file_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=255), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["grading_result_id"],
            ["grading_results.id"],
            name=op.f("fk_grading_evidence_grading_result_id_grading_results"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submission_file_id"],
            ["submission_files.id"],
            name=op.f("fk_grading_evidence_submission_file_id_submission_files"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grading_evidence")),
        **table_options,
    )
    op.create_index(
        op.f("ix_grading_evidence_grading_result_id"),
        "grading_evidence",
        ["grading_result_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grading_evidence_submission_file_id"),
        "grading_evidence",
        ["submission_file_id"],
        unique=False,
    )

    op.create_table(
        "viva_questions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("grading_run_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(length=16), server_default="MEDIUM", nullable=False),
        sa.Column("source_file", sa.String(length=1024), nullable=True),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["grading_run_id"],
            ["grading_runs.id"],
            name=op.f("fk_viva_questions_grading_run_id_grading_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_viva_questions")),
        **table_options,
    )
    op.create_index(
        op.f("ix_viva_questions_grading_run_id"),
        "viva_questions",
        ["grading_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_viva_questions_grading_run_id"), table_name="viva_questions")
    op.drop_table("viva_questions")
    op.drop_index(op.f("ix_grading_evidence_submission_file_id"), table_name="grading_evidence")
    op.drop_index(op.f("ix_grading_evidence_grading_result_id"), table_name="grading_evidence")
    op.drop_table("grading_evidence")
    op.drop_index(op.f("ix_grading_results_rubric_item_id"), table_name="grading_results")
    op.drop_index(op.f("ix_grading_results_grading_run_id"), table_name="grading_results")
    op.drop_table("grading_results")
    op.drop_index(op.f("ix_grading_runs_submission_id"), table_name="grading_runs")
    op.drop_table("grading_runs")
    op.drop_index(op.f("ix_submission_files_submission_id"), table_name="submission_files")
    op.drop_table("submission_files")
    op.drop_index(op.f("ix_submissions_student_id"), table_name="submissions")
    op.drop_index(op.f("ix_submissions_rubric_id"), table_name="submissions")
    op.drop_index(op.f("ix_submissions_assignment_id"), table_name="submissions")
    op.drop_table("submissions")
    op.drop_index(op.f("ix_rubric_items_rubric_id"), table_name="rubric_items")
    op.drop_table("rubric_items")
    op.drop_index(op.f("ix_rubrics_assignment_id"), table_name="rubrics")
    op.drop_table("rubrics")
    op.drop_table("students")
    op.drop_index(op.f("ix_assignments_created_by"), table_name="assignments")
    op.drop_table("assignments")
    op.drop_table("users")
