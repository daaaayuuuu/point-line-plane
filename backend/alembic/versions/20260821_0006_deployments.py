"""preview acceptance and controlled deployments

Revision ID: 20260821_0006
Revises: 20260821_0005
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0006"
down_revision: str | None = "20260821_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "preview_acceptances",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("preview_id", sa.String(length=36), nullable=False),
        sa.Column("code_version_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("checklist_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["code_version_id"], ["code_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preview_id"], ["previews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_preview_acceptances_project_id", "preview_acceptances", ["project_id"])
    op.create_index(
        "ix_preview_acceptances_preview_id", "preview_acceptances", ["preview_id"], unique=True
    )
    op.create_index(
        "ix_preview_acceptances_code_version_id", "preview_acceptances", ["code_version_id"]
    )
    op.create_index("ix_preview_acceptances_actor_id", "preview_acceptances", ["actor_id"])

    op.create_table(
        "deployment_authorizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("credential_ref_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("target_deployment_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("region", sa.String(length=60), nullable=False),
        sa.Column("environment", sa.String(length=30), nullable=False),
        sa.Column("permission_scope_json", sa.JSON(), nullable=False),
        sa.Column("estimated_cost_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["credential_ref_id"], ["credential_refs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name in (
        "project_id",
        "actor_id",
        "credential_ref_id",
        "action",
        "status",
        "expires_at",
    ):
        op.create_index(
            f"ix_deployment_authorizations_{name}", "deployment_authorizations", [name]
        )

    op.create_table(
        "deployments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("preview_id", sa.String(length=36), nullable=False),
        sa.Column("code_version_id", sa.String(length=36), nullable=False),
        sa.Column("credential_ref_id", sa.String(length=36), nullable=False),
        sa.Column("authorization_id", sa.String(length=36), nullable=False),
        sa.Column("previous_deployment_id", sa.String(length=36), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("region", sa.String(length=60), nullable=False),
        sa.Column("environment", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider_ref", sa.String(length=200), nullable=True),
        sa.Column("deployment_url", sa.String(length=500), nullable=True),
        sa.Column("checkpoint_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("trace_id", sa.String(length=36), nullable=False),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["authorization_id"], ["deployment_authorizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["code_version_id"], ["code_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["credential_ref_id"], ["credential_refs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["previous_deployment_id"], ["deployments.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["preview_id"], ["previews.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "revision"),
    )
    for name in (
        "project_id",
        "preview_id",
        "code_version_id",
        "credential_ref_id",
        "previous_deployment_id",
        "status",
        "trace_id",
    ):
        op.create_index(f"ix_deployments_{name}", "deployments", [name])
    op.create_index(
        "ix_deployments_authorization_id", "deployments", ["authorization_id"], unique=True
    )

    op.create_table(
        "deployment_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deployment_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("message", sa.String(length=240), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deployment_id", "sequence"),
    )
    op.create_index(
        "ix_deployment_events_deployment_id", "deployment_events", ["deployment_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_deployment_events_deployment_id", table_name="deployment_events")
    op.drop_table("deployment_events")
    op.drop_index("ix_deployments_authorization_id", table_name="deployments")
    for name in (
        "trace_id",
        "status",
        "previous_deployment_id",
        "credential_ref_id",
        "code_version_id",
        "preview_id",
        "project_id",
    ):
        op.drop_index(f"ix_deployments_{name}", table_name="deployments")
    op.drop_table("deployments")
    for name in (
        "expires_at",
        "status",
        "action",
        "credential_ref_id",
        "actor_id",
        "project_id",
    ):
        op.drop_index(
            f"ix_deployment_authorizations_{name}", table_name="deployment_authorizations"
        )
    op.drop_table("deployment_authorizations")
    op.drop_index("ix_preview_acceptances_actor_id", table_name="preview_acceptances")
    op.drop_index("ix_preview_acceptances_code_version_id", table_name="preview_acceptances")
    op.drop_index("ix_preview_acceptances_preview_id", table_name="preview_acceptances")
    op.drop_index("ix_preview_acceptances_project_id", table_name="preview_acceptances")
    op.drop_table("preview_acceptances")
