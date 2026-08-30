"""quality gates, repair attempts and generated runtime previews

Revision ID: 20260821_0004
Revises: 20260821_0003
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0004"
down_revision: str | None = "20260821_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quality_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("development_run_id", sa.String(length=36), nullable=False),
        sa.Column("code_version_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("output_excerpt", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["code_version_id"], ["code_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["development_run_id"], ["development_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "sequence"),
    )
    op.create_index("ix_quality_runs_project_id", "quality_runs", ["project_id"])
    op.create_index("ix_quality_runs_task_id", "quality_runs", ["task_id"])
    op.create_index("ix_quality_runs_development_run_id", "quality_runs", ["development_run_id"])
    op.create_index("ix_quality_runs_code_version_id", "quality_runs", ["code_version_id"])
    op.create_index("ix_quality_runs_kind", "quality_runs", ["kind"])
    op.create_index("ix_quality_runs_status", "quality_runs", ["status"])

    op.create_table(
        "repair_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("development_run_id", sa.String(length=36), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_code_version_id", sa.String(length=36), nullable=False),
        sa.Column("repaired_code_version_id", sa.String(length=36), nullable=True),
        sa.Column("failure_summary_json", sa.JSON(), nullable=False),
        sa.Column("strategy_summary", sa.String(length=300), nullable=False),
        sa.Column("usage_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["development_run_id"], ["development_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repaired_code_version_id"], ["code_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_code_version_id"], ["code_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "attempt"),
    )
    op.create_index("ix_repair_attempts_project_id", "repair_attempts", ["project_id"])
    op.create_index("ix_repair_attempts_task_id", "repair_attempts", ["task_id"])
    op.create_index("ix_repair_attempts_development_run_id", "repair_attempts", ["development_run_id"])
    op.create_index("ix_repair_attempts_source_code_version_id", "repair_attempts", ["source_code_version_id"])
    op.create_index("ix_repair_attempts_status", "repair_attempts", ["status"])

    op.create_table(
        "preview_runtimes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("preview_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("code_version_id", sa.String(length=36), nullable=False),
        sa.Column("runtime_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("process_ref", sa.String(length=36), nullable=False),
        sa.Column("host", sa.String(length=80), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("base_url", sa.String(length=300), nullable=True),
        sa.Column("health_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["code_version_id"], ["code_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preview_id"], ["previews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_preview_runtimes_preview_id", "preview_runtimes", ["preview_id"], unique=True)
    op.create_index("ix_preview_runtimes_project_id", "preview_runtimes", ["project_id"])
    op.create_index("ix_preview_runtimes_code_version_id", "preview_runtimes", ["code_version_id"])
    op.create_index("ix_preview_runtimes_process_ref", "preview_runtimes", ["process_ref"], unique=True)
    op.create_index("ix_preview_runtimes_status", "preview_runtimes", ["status"])


def downgrade() -> None:
    op.drop_index("ix_preview_runtimes_status", table_name="preview_runtimes")
    op.drop_index("ix_preview_runtimes_process_ref", table_name="preview_runtimes")
    op.drop_index("ix_preview_runtimes_code_version_id", table_name="preview_runtimes")
    op.drop_index("ix_preview_runtimes_project_id", table_name="preview_runtimes")
    op.drop_index("ix_preview_runtimes_preview_id", table_name="preview_runtimes")
    op.drop_table("preview_runtimes")
    op.drop_index("ix_repair_attempts_status", table_name="repair_attempts")
    op.drop_index("ix_repair_attempts_source_code_version_id", table_name="repair_attempts")
    op.drop_index("ix_repair_attempts_development_run_id", table_name="repair_attempts")
    op.drop_index("ix_repair_attempts_task_id", table_name="repair_attempts")
    op.drop_index("ix_repair_attempts_project_id", table_name="repair_attempts")
    op.drop_table("repair_attempts")
    op.drop_index("ix_quality_runs_status", table_name="quality_runs")
    op.drop_index("ix_quality_runs_kind", table_name="quality_runs")
    op.drop_index("ix_quality_runs_code_version_id", table_name="quality_runs")
    op.drop_index("ix_quality_runs_development_run_id", table_name="quality_runs")
    op.drop_index("ix_quality_runs_task_id", table_name="quality_runs")
    op.drop_index("ix_quality_runs_project_id", table_name="quality_runs")
    op.drop_table("quality_runs")
