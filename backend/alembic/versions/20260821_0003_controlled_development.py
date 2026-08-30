"""Add controlled development workspaces, runs, tools and code file metadata.

Revision ID: 20260821_0003
Revises: 20260820_0002
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0003"
down_revision: str | None = "20260820_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "development_workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("relative_path", sa.String(length=120), nullable=False),
        sa.Column("runtime_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_commit_ref", sa.String(length=40), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
        sa.UniqueConstraint("relative_path"),
    )
    op.create_index(
        op.f("ix_development_workspaces_project_id"),
        "development_workspaces",
        ["project_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_development_workspaces_status"),
        "development_workspaces",
        ["status"],
    )

    op.create_table(
        "development_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("solution_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("code_version_id", sa.String(length=36), nullable=True),
        sa.Column("resumed_from_run_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_step", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("provider_verification", sa.String(length=20), nullable=True),
        sa.Column("plan_json", sa.JSON(), nullable=False),
        sa.Column("budget_json", sa.JSON(), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("usage_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["code_version_id"], ["code_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["resumed_from_run_id"], ["development_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["solution_artifact_id"], ["artifacts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["development_workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_version_id"),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index(
        op.f("ix_development_runs_idempotency_key"),
        "development_runs",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(op.f("ix_development_runs_project_id"), "development_runs", ["project_id"])
    op.create_index(op.f("ix_development_runs_status"), "development_runs", ["status"])
    op.create_index(
        op.f("ix_development_runs_solution_artifact_id"),
        "development_runs",
        ["solution_artifact_id"],
    )
    op.create_index(
        op.f("ix_development_runs_task_id"),
        "development_runs",
        ["task_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_development_runs_workspace_id"),
        "development_runs",
        ["workspace_id"],
    )

    op.create_table(
        "tool_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=60), nullable=False),
        sa.Column("side_effect", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("input_summary_json", sa.JSON(), nullable=False),
        sa.Column("output_summary_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["development_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sequence"),
    )
    op.create_index(op.f("ix_tool_executions_run_id"), "tool_executions", ["run_id"])

    op.create_table(
        "code_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code_version_id", sa.String(length=36), nullable=False),
        sa.Column("path", sa.String(length=240), nullable=False),
        sa.Column("language", sa.String(length=40), nullable=False),
        sa.Column("product_purpose", sa.String(length=300), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["code_version_id"], ["code_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_version_id", "path"),
    )
    op.create_index(op.f("ix_code_files_code_version_id"), "code_files", ["code_version_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_code_files_code_version_id"), table_name="code_files")
    op.drop_table("code_files")
    op.drop_index(op.f("ix_tool_executions_run_id"), table_name="tool_executions")
    op.drop_table("tool_executions")
    op.drop_index(op.f("ix_development_runs_workspace_id"), table_name="development_runs")
    op.drop_index(op.f("ix_development_runs_task_id"), table_name="development_runs")
    op.drop_index(
        op.f("ix_development_runs_solution_artifact_id"), table_name="development_runs"
    )
    op.drop_index(op.f("ix_development_runs_status"), table_name="development_runs")
    op.drop_index(op.f("ix_development_runs_project_id"), table_name="development_runs")
    op.drop_index(op.f("ix_development_runs_idempotency_key"), table_name="development_runs")
    op.drop_table("development_runs")
    op.drop_index(
        op.f("ix_development_workspaces_status"), table_name="development_workspaces"
    )
    op.drop_index(
        op.f("ix_development_workspaces_project_id"), table_name="development_workspaces"
    )
    op.drop_table("development_workspaces")
