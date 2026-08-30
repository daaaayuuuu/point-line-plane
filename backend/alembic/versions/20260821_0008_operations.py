"""beta invites, persistent rate limiting and backups

Revision ID: 20260821_0008
Revises: 20260821_0007
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0008"
down_revision: str | None = "20260821_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "beta_invites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_beta_invites_code_hash", "beta_invites", ["code_hash"], unique=True)
    op.create_index("ix_beta_invites_status", "beta_invites", ["status"])
    op.create_index("ix_beta_invites_expires_at", "beta_invites", ["expires_at"])

    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rate_limit_events_key_hash", "rate_limit_events", ["key_hash"])
    op.create_index("ix_rate_limit_events_action", "rate_limit_events", ["action"])
    op.create_index("ix_rate_limit_events_occurred_at", "rate_limit_events", ["occurred_at"])

    op.create_table(
        "backup_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("storage_ref", sa.String(length=300), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_ref"),
    )
    op.create_index("ix_backup_records_status", "backup_records", ["status"])


def downgrade() -> None:
    op.drop_index("ix_backup_records_status", table_name="backup_records")
    op.drop_table("backup_records")
    op.drop_index("ix_rate_limit_events_occurred_at", table_name="rate_limit_events")
    op.drop_index("ix_rate_limit_events_action", table_name="rate_limit_events")
    op.drop_index("ix_rate_limit_events_key_hash", table_name="rate_limit_events")
    op.drop_table("rate_limit_events")
    op.drop_index("ix_beta_invites_expires_at", table_name="beta_invites")
    op.drop_index("ix_beta_invites_status", table_name="beta_invites")
    op.drop_index("ix_beta_invites_code_hash", table_name="beta_invites")
    op.drop_table("beta_invites")
