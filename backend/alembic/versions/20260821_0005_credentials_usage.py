"""encrypted credential references, quota, usage and cost authorization

Revision ID: 20260821_0005
Revises: 20260821_0004
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0005"
down_revision: str | None = "20260821_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credential_refs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("scope", sa.String(length=30), nullable=False),
        sa.Column("secret_ref", sa.String(length=120), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("masked_hint", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("secret_ref"),
    )
    op.create_index("ix_credential_refs_owner_id", "credential_refs", ["owner_id"])
    op.create_index("ix_credential_refs_project_id", "credential_refs", ["project_id"])
    op.create_index("ix_credential_refs_provider", "credential_refs", ["provider"])
    op.create_index("ix_credential_refs_scope", "credential_refs", ["scope"])
    op.create_index("ix_credential_refs_fingerprint", "credential_refs", ["fingerprint"])
    op.create_index("ix_credential_refs_status", "credential_refs", ["status"])
    op.create_index("ix_credential_refs_expires_at", "credential_refs", ["expires_at"])

    op.create_table(
        "quota_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("plan", sa.String(length=30), nullable=False),
        sa.Column("granted_units", sa.Integer(), nullable=False),
        sa.Column("consumed_units", sa.Integer(), nullable=False),
        sa.Column("reserved_units", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quota_accounts_user_id", "quota_accounts", ["user_id"], unique=True)

    op.create_table(
        "usage_ledgers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("credential_ref_id", sa.String(length=36), nullable=True),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("quota_units", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_microusd", sa.Integer(), nullable=False),
        sa.Column("pricing_configured", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("usage_json", sa.JSON(), nullable=False),
        sa.Column("trace_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["credential_ref_id"], ["credential_refs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name in (
        "owner_id",
        "project_id",
        "task_id",
        "credential_ref_id",
        "operation",
        "source",
        "status",
        "trace_id",
    ):
        op.create_index(f"ix_usage_ledgers_{name}", "usage_ledgers", [name])

    op.create_table(
        "cost_authorizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("credential_ref_id", sa.String(length=36), nullable=True),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_quota_units", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_microusd", sa.Integer(), nullable=False),
        sa.Column("pricing_configured", sa.Boolean(), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["credential_ref_id"], ["credential_refs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name in (
        "owner_id",
        "project_id",
        "credential_ref_id",
        "operation",
        "status",
        "expires_at",
    ):
        op.create_index(f"ix_cost_authorizations_{name}", "cost_authorizations", [name])


def downgrade() -> None:
    for name in (
        "expires_at",
        "status",
        "operation",
        "credential_ref_id",
        "project_id",
        "owner_id",
    ):
        op.drop_index(f"ix_cost_authorizations_{name}", table_name="cost_authorizations")
    op.drop_table("cost_authorizations")
    for name in (
        "trace_id",
        "status",
        "source",
        "operation",
        "credential_ref_id",
        "task_id",
        "project_id",
        "owner_id",
    ):
        op.drop_index(f"ix_usage_ledgers_{name}", table_name="usage_ledgers")
    op.drop_table("usage_ledgers")
    op.drop_index("ix_quota_accounts_user_id", table_name="quota_accounts")
    op.drop_table("quota_accounts")
    for name in (
        "expires_at",
        "status",
        "fingerprint",
        "scope",
        "provider",
        "project_id",
        "owner_id",
    ):
        op.drop_index(f"ix_credential_refs_{name}", table_name="credential_refs")
    op.drop_table("credential_refs")
