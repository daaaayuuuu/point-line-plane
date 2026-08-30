"""Add visual product model, decisions and user simulation records.

Revision ID: 20260820_0002
Revises: 20260820_0001
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260820_0002"
down_revision: str | None = "20260820_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_graphs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("product_goal", sa.Text(), nullable=False),
        sa.Column("source_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("base_code_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["base_code_version_id"], ["code_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "version"),
    )
    op.create_index(op.f("ix_product_graphs_project_id"), "product_graphs", ["project_id"])
    op.create_index(op.f("ix_product_graphs_status"), "product_graphs", ["status"])

    op.create_table(
        "journey_nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("graph_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("node_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("caption", sa.String(length=240), nullable=False),
        sa.Column("product_purpose", sa.Text(), nullable=False),
        sa.Column("user_sees", sa.Text(), nullable=False),
        sa.Column("system_does", sa.Text(), nullable=False),
        sa.Column("technical_contract_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["graph_id"], ["product_graphs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("graph_id", "key"),
        sa.UniqueConstraint("graph_id", "position"),
    )
    op.create_index(op.f("ix_journey_nodes_graph_id"), "journey_nodes", ["graph_id"])

    op.create_table(
        "product_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("graph_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("selected_option_key", sa.String(length=80), nullable=True),
        sa.Column("confirmation_key", sa.String(length=120), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["graph_id"], ["product_graphs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["journey_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("graph_id", "key"),
    )
    op.create_index(
        op.f("ix_product_decisions_confirmation_key"),
        "product_decisions",
        ["confirmation_key"],
        unique=True,
    )
    op.create_index(op.f("ix_product_decisions_graph_id"), "product_decisions", ["graph_id"])
    op.create_index(op.f("ix_product_decisions_node_id"), "product_decisions", ["node_id"])
    op.create_index(op.f("ix_product_decisions_project_id"), "product_decisions", ["project_id"])
    op.create_index(op.f("ix_product_decisions_status"), "product_decisions", ["status"])

    op.create_table(
        "decision_options",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("decision_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("recommended", sa.Boolean(), nullable=False),
        sa.Column("product_impact_json", sa.JSON(), nullable=False),
        sa.Column("technical_effects_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["decision_id"], ["product_decisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_id", "key"),
    )
    op.create_index(op.f("ix_decision_options_decision_id"), "decision_options", ["decision_id"])

    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("graph_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("persona_key", sa.String(length=60), nullable=False),
        sa.Column("persona_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_node_id", sa.String(length=36), nullable=True),
        sa.Column("checkpoint_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["current_node_id"], ["journey_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["graph_id"], ["product_graphs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_simulation_runs_graph_id"), "simulation_runs", ["graph_id"])
    op.create_index(
        op.f("ix_simulation_runs_idempotency_key"),
        "simulation_runs",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(op.f("ix_simulation_runs_project_id"), "simulation_runs", ["project_id"])
    op.create_index(op.f("ix_simulation_runs_status"), "simulation_runs", ["status"])

    op.create_table(
        "simulation_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("observation", sa.Text(), nullable=False),
        sa.Column("technical_evidence_json", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["journey_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sequence"),
    )
    op.create_index(op.f("ix_simulation_steps_node_id"), "simulation_steps", ["node_id"])
    op.create_index(op.f("ix_simulation_steps_run_id"), "simulation_steps", ["run_id"])

    op.create_table(
        "friction_findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("product_summary", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("resolution_key", sa.String(length=80), nullable=True),
        sa.Column("resolution_idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["journey_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_friction_findings_node_id"), "friction_findings", ["node_id"])
    op.create_index(
        op.f("ix_friction_findings_resolution_idempotency_key"),
        "friction_findings",
        ["resolution_idempotency_key"],
        unique=True,
    )
    op.create_index(op.f("ix_friction_findings_run_id"), "friction_findings", ["run_id"])
    op.create_index(op.f("ix_friction_findings_status"), "friction_findings", ["status"])

    op.create_table(
        "product_change_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("graph_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("scope_classification", sa.String(length=20), nullable=False),
        sa.Column("product_request", sa.Text(), nullable=False),
        sa.Column("product_impact_json", sa.JSON(), nullable=False),
        sa.Column("technical_context_json", sa.JSON(), nullable=False),
        sa.Column("base_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("base_code_version_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["base_artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["base_code_version_id"], ["code_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["graph_id"], ["product_graphs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["journey_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_product_change_requests_graph_id"), "product_change_requests", ["graph_id"])
    op.create_index(
        op.f("ix_product_change_requests_idempotency_key"),
        "product_change_requests",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(op.f("ix_product_change_requests_node_id"), "product_change_requests", ["node_id"])
    op.create_index(op.f("ix_product_change_requests_project_id"), "product_change_requests", ["project_id"])
    op.create_index(op.f("ix_product_change_requests_source_id"), "product_change_requests", ["source_id"])
    op.create_index(op.f("ix_product_change_requests_status"), "product_change_requests", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_product_change_requests_status"), table_name="product_change_requests")
    op.drop_index(op.f("ix_product_change_requests_source_id"), table_name="product_change_requests")
    op.drop_index(op.f("ix_product_change_requests_project_id"), table_name="product_change_requests")
    op.drop_index(op.f("ix_product_change_requests_node_id"), table_name="product_change_requests")
    op.drop_index(op.f("ix_product_change_requests_idempotency_key"), table_name="product_change_requests")
    op.drop_index(op.f("ix_product_change_requests_graph_id"), table_name="product_change_requests")
    op.drop_table("product_change_requests")

    op.drop_index(op.f("ix_friction_findings_status"), table_name="friction_findings")
    op.drop_index(op.f("ix_friction_findings_run_id"), table_name="friction_findings")
    op.drop_index(
        op.f("ix_friction_findings_resolution_idempotency_key"),
        table_name="friction_findings",
    )
    op.drop_index(op.f("ix_friction_findings_node_id"), table_name="friction_findings")
    op.drop_table("friction_findings")

    op.drop_index(op.f("ix_simulation_steps_run_id"), table_name="simulation_steps")
    op.drop_index(op.f("ix_simulation_steps_node_id"), table_name="simulation_steps")
    op.drop_table("simulation_steps")

    op.drop_index(op.f("ix_simulation_runs_status"), table_name="simulation_runs")
    op.drop_index(op.f("ix_simulation_runs_project_id"), table_name="simulation_runs")
    op.drop_index(op.f("ix_simulation_runs_idempotency_key"), table_name="simulation_runs")
    op.drop_index(op.f("ix_simulation_runs_graph_id"), table_name="simulation_runs")
    op.drop_table("simulation_runs")

    op.drop_index(op.f("ix_decision_options_decision_id"), table_name="decision_options")
    op.drop_table("decision_options")

    op.drop_index(op.f("ix_product_decisions_status"), table_name="product_decisions")
    op.drop_index(op.f("ix_product_decisions_project_id"), table_name="product_decisions")
    op.drop_index(op.f("ix_product_decisions_node_id"), table_name="product_decisions")
    op.drop_index(op.f("ix_product_decisions_graph_id"), table_name="product_decisions")
    op.drop_index(op.f("ix_product_decisions_confirmation_key"), table_name="product_decisions")
    op.drop_table("product_decisions")

    op.drop_index(op.f("ix_journey_nodes_graph_id"), table_name="journey_nodes")
    op.drop_table("journey_nodes")

    op.drop_index(op.f("ix_product_graphs_status"), table_name="product_graphs")
    op.drop_index(op.f("ix_product_graphs_project_id"), table_name="product_graphs")
    op.drop_table("product_graphs")
