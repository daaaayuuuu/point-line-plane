"""delivery packages and GitHub synchronization records

Revision ID: 20260821_0007
Revises: 20260821_0006
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0007"
down_revision: str | None = "20260821_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delivery_packages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("deployment_id", sa.String(length=36), nullable=False),
        sa.Column("code_version_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("storage_path", sa.String(length=240), nullable=False),
        sa.Column("filename", sa.String(length=180), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["code_version_id"], ["code_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "revision"),
        sa.UniqueConstraint("storage_path"),
    )
    op.create_index("ix_delivery_packages_project_id", "delivery_packages", ["project_id"])
    op.create_index("ix_delivery_packages_deployment_id", "delivery_packages", ["deployment_id"])
    op.create_index("ix_delivery_packages_code_version_id", "delivery_packages", ["code_version_id"])
    op.create_index("ix_delivery_packages_status", "delivery_packages", ["status"])

    op.create_table(
        "github_syncs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("delivery_package_id", sa.String(length=36), nullable=False),
        sa.Column("repository_full_name", sa.String(length=200), nullable=False),
        sa.Column("branch", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider_ref", sa.String(length=200), nullable=True),
        sa.Column("repository_url", sa.String(length=500), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["delivery_package_id"], ["delivery_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name in ("owner_id", "project_id", "delivery_package_id", "status"):
        op.create_index(f"ix_github_syncs_{name}", "github_syncs", [name])


def downgrade() -> None:
    for name in ("status", "delivery_package_id", "project_id", "owner_id"):
        op.drop_index(f"ix_github_syncs_{name}", table_name="github_syncs")
    op.drop_table("github_syncs")
    op.drop_index("ix_delivery_packages_status", table_name="delivery_packages")
    op.drop_index("ix_delivery_packages_code_version_id", table_name="delivery_packages")
    op.drop_index("ix_delivery_packages_deployment_id", table_name="delivery_packages")
    op.drop_index("ix_delivery_packages_project_id", table_name="delivery_packages")
    op.drop_table("delivery_packages")
