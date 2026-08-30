from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.models.enums import (
    ArtifactStatus,
    ProjectStage,
    ProjectStatus,
    TaskStatus,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    display_name: Mapped[str] = mapped_column(String(80))
    invite_code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    quota: Mapped[dict[str, Any]] = mapped_column(JSON, default=lambda: {"projects": 10})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[list[Project]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="sessions")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    idea: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(
        String(32), default=ProjectStage.REQUIREMENTS.value, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=ProjectStatus.ACTIVE.value)
    scope: Mapped[str] = mapped_column(String(50), default="text_ai_agent")
    current_artifact_version: Mapped[int] = mapped_column(Integer, default=0)
    development_revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    owner: Mapped[User] = relationship(back_populates="projects")
    requirement_session: Mapped[RequirementSession | None] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    confirmations: Mapped[list[Confirmation]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    tasks: Mapped[list[Task]] = relationship(back_populates="project", cascade="all, delete-orphan")
    code_versions: Mapped[list[CodeVersion]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    previews: Mapped[list[Preview]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    product_graphs: Mapped[list[ProductGraph]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    development_workspace: Mapped[DevelopmentWorkspace | None] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    development_runs: Mapped[list[DevelopmentRun]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class RequirementSession(Base):
    __tablename__ = "requirement_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True, index=True
    )
    answers_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=lambda: {"messages": []})
    missing_items_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    round: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)

    project: Mapped[Project] = relationship(back_populates="requirement_session")


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("project_id", "type", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(30), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=ArtifactStatus.DRAFT.value)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="artifacts")
    confirmations: Mapped[list[Confirmation]] = relationship(back_populates="artifact")


class Confirmation(Base):
    __tablename__ = "confirmations"
    __table_args__ = (UniqueConstraint("artifact_id", "decision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(30))
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="confirmations")
    artifact: Mapped[Artifact] = relationship(back_populates="confirmations")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    stage: Mapped[str] = mapped_column(String(32), default=ProjectStage.DEVELOPMENT.value)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.QUEUED.value, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2)
    budget_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    checkpoint_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="tasks")
    events: Mapped[list[TaskEvent]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskEvent.sequence"
    )


class TaskEvent(Base):
    __tablename__ = "task_events"
    __table_args__ = (UniqueConstraint("task_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(240))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task: Mapped[Task] = relationship(back_populates="events")


class CodeVersion(Base):
    __tablename__ = "code_versions"
    __table_args__ = (UniqueConstraint("project_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    commit_ref: Mapped[str] = mapped_column(String(64))
    test_status: Mapped[str] = mapped_column(String(20))
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="code_versions")
    previews: Mapped[list[Preview]] = relationship(back_populates="code_version")
    files: Mapped[list[CodeFile]] = relationship(
        back_populates="code_version", cascade="all, delete-orphan"
    )


class Preview(Base):
    __tablename__ = "previews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    code_version_id: Mapped[str] = mapped_column(
        ForeignKey("code_versions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="ready")
    preview_token: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    url_path: Mapped[str] = mapped_column(String(200))
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="previews")
    code_version: Mapped[CodeVersion] = relationship(back_populates="previews")
    runs: Mapped[list[PreviewRun]] = relationship(
        back_populates="preview", cascade="all, delete-orphan", order_by="PreviewRun.created_at"
    )


class PreviewRun(Base):
    __tablename__ = "preview_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    preview_id: Mapped[str] = mapped_column(
        ForeignKey("previews.id", ondelete="CASCADE"), index=True
    )
    input_text: Mapped[str] = mapped_column(Text)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100))
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    preview: Mapped[Preview] = relationship(back_populates="runs")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(80))
    target_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result: Mapped[str] = mapped_column(String(30))
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProductGraph(Base):
    __tablename__ = "product_graphs"
    __table_args__ = (UniqueConstraint("project_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    title: Mapped[str] = mapped_column(String(160))
    product_goal: Mapped[str] = mapped_column(Text)
    source_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    base_code_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("code_versions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="product_graphs")
    nodes: Mapped[list[JourneyNode]] = relationship(
        back_populates="graph", cascade="all, delete-orphan", order_by="JourneyNode.position"
    )
    decisions: Mapped[list[ProductDecision]] = relationship(
        back_populates="graph", cascade="all, delete-orphan"
    )
    simulations: Mapped[list[SimulationRun]] = relationship(
        back_populates="graph", cascade="all, delete-orphan"
    )


class JourneyNode(Base):
    __tablename__ = "journey_nodes"
    __table_args__ = (
        UniqueConstraint("graph_id", "key"),
        UniqueConstraint("graph_id", "position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    graph_id: Mapped[str] = mapped_column(
        ForeignKey("product_graphs.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer)
    node_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="ready")
    title: Mapped[str] = mapped_column(String(120))
    caption: Mapped[str] = mapped_column(String(240))
    product_purpose: Mapped[str] = mapped_column(Text)
    user_sees: Mapped[str] = mapped_column(Text)
    system_does: Mapped[str] = mapped_column(Text)
    technical_contract_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    graph: Mapped[ProductGraph] = relationship(back_populates="nodes")
    decisions: Mapped[list[ProductDecision]] = relationship(back_populates="node")
    steps: Mapped[list[SimulationStep]] = relationship(back_populates="node")
    findings: Mapped[list[FrictionFinding]] = relationship(back_populates="node")


class ProductDecision(Base):
    __tablename__ = "product_decisions"
    __table_args__ = (UniqueConstraint("graph_id", "key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    graph_id: Mapped[str] = mapped_column(
        ForeignKey("product_graphs.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("journey_nodes.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    title: Mapped[str] = mapped_column(String(160))
    question: Mapped[str] = mapped_column(Text)
    selected_option_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confirmation_key: Mapped[str | None] = mapped_column(
        String(120), nullable=True, unique=True, index=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    graph: Mapped[ProductGraph] = relationship(back_populates="decisions")
    node: Mapped[JourneyNode] = relationship(back_populates="decisions")
    options: Mapped[list[DecisionOption]] = relationship(
        back_populates="decision", cascade="all, delete-orphan", order_by="DecisionOption.position"
    )


class DecisionOption(Base):
    __tablename__ = "decision_options"
    __table_args__ = (UniqueConstraint("decision_id", "key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    decision_id: Mapped[str] = mapped_column(
        ForeignKey("product_decisions.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    recommended: Mapped[bool] = mapped_column(default=False)
    product_impact_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    technical_effects_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    decision: Mapped[ProductDecision] = relationship(back_populates="options")


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    graph_id: Mapped[str] = mapped_column(
        ForeignKey("product_graphs.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    persona_key: Mapped[str] = mapped_column(String(60))
    persona_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    current_node_id: Mapped[str | None] = mapped_column(
        ForeignKey("journey_nodes.id", ondelete="SET NULL"), nullable=True
    )
    checkpoint_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    graph: Mapped[ProductGraph] = relationship(back_populates="simulations")
    steps: Mapped[list[SimulationStep]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="SimulationStep.sequence"
    )
    findings: Mapped[list[FrictionFinding]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class SimulationStep(Base):
    __tablename__ = "simulation_steps"
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("journey_nodes.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    observation: Mapped[str] = mapped_column(Text)
    technical_evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[SimulationRun] = relationship(back_populates="steps")
    node: Mapped[JourneyNode] = relationship(back_populates="steps")


class FrictionFinding(Base):
    __tablename__ = "friction_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("simulation_runs.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("journey_nodes.id", ondelete="CASCADE"), index=True
    )
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    product_summary: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    resolution_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resolution_idempotency_key: Mapped[str | None] = mapped_column(
        String(120), nullable=True, unique=True, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[SimulationRun] = relationship(back_populates="findings")
    node: Mapped[JourneyNode] = relationship(back_populates="findings")


class ProductChangeRequest(Base):
    __tablename__ = "product_change_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    graph_id: Mapped[str] = mapped_column(
        ForeignKey("product_graphs.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str | None] = mapped_column(
        ForeignKey("journey_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), default="confirmed", index=True)
    scope_classification: Mapped[str] = mapped_column(String(20), default="in_scope")
    product_request: Mapped[str] = mapped_column(Text)
    product_impact_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    technical_context_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    base_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    base_code_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("code_versions.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DevelopmentWorkspace(Base):
    __tablename__ = "development_workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True, index=True
    )
    relative_path: Mapped[str] = mapped_column(String(120), unique=True)
    runtime_type: Mapped[str] = mapped_column(String(40), default="controlled_code_bundle_v1")
    status: Mapped[str] = mapped_column(String(20), default="ready", index=True)
    current_commit_ref: Mapped[str | None] = mapped_column(String(40), nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="development_workspace")
    runs: Mapped[list[DevelopmentRun]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class DevelopmentRun(Base):
    __tablename__ = "development_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("development_workspaces.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), unique=True, index=True
    )
    solution_artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="RESTRICT"), index=True
    )
    code_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("code_versions.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    resumed_from_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("development_runs.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    current_step: Mapped[str] = mapped_column(String(50), default="accepted")
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_verification: Mapped[str | None] = mapped_column(String(20), nullable=True)
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    budget_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="development_runs")
    workspace: Mapped[DevelopmentWorkspace] = relationship(back_populates="runs")
    tools: Mapped[list[ToolExecution]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="ToolExecution.sequence"
    )


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("development_runs.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str] = mapped_column(String(60))
    side_effect: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="running")
    input_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[DevelopmentRun] = relationship(back_populates="tools")


class CodeFile(Base):
    __tablename__ = "code_files"
    __table_args__ = (UniqueConstraint("code_version_id", "path"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code_version_id: Mapped[str] = mapped_column(
        ForeignKey("code_versions.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(String(240))
    language: Mapped[str] = mapped_column(String(40))
    product_purpose: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    code_version: Mapped[CodeVersion] = relationship(back_populates="files")


class QualityRun(Base):
    __tablename__ = "quality_runs"
    __table_args__ = (UniqueConstraint("task_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    development_run_id: Mapped[str] = mapped_column(
        ForeignKey("development_runs.id", ondelete="CASCADE"), index=True
    )
    code_version_id: Mapped[str] = mapped_column(
        ForeignKey("code_versions.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_excerpt: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RepairAttempt(Base):
    __tablename__ = "repair_attempts"
    __table_args__ = (UniqueConstraint("task_id", "attempt"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    development_run_id: Mapped[str] = mapped_column(
        ForeignKey("development_runs.id", ondelete="CASCADE"), index=True
    )
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), index=True)
    source_code_version_id: Mapped[str] = mapped_column(
        ForeignKey("code_versions.id", ondelete="CASCADE"), index=True
    )
    repaired_code_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("code_versions.id", ondelete="SET NULL"), nullable=True
    )
    failure_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    strategy_summary: Mapped[str] = mapped_column(String(300))
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PreviewRuntime(Base):
    __tablename__ = "preview_runtimes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    preview_id: Mapped[str] = mapped_column(
        ForeignKey("previews.id", ondelete="CASCADE"), unique=True, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    code_version_id: Mapped[str] = mapped_column(
        ForeignKey("code_versions.id", ondelete="CASCADE"), index=True
    )
    runtime_type: Mapped[str] = mapped_column(String(40), default="trusted_mock_subprocess")
    status: Mapped[str] = mapped_column(String(20), index=True, default="provisioning")
    process_ref: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    host: Mapped[str] = mapped_column(String(80), default="127.0.0.1")
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    health_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CredentialRef(Base):
    __tablename__ = "credential_refs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(40), index=True)
    model: Mapped[str] = mapped_column(String(120))
    scope: Mapped[str] = mapped_column(String(30), index=True)
    secret_ref: Mapped[str] = mapped_column(String(120), unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    masked_hint: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), index=True, default="unverified")
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class QuotaAccount(Base):
    __tablename__ = "quota_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    plan: Mapped[str] = mapped_column(String(30), default="internal_free")
    granted_units: Mapped[int] = mapped_column(Integer, default=0)
    consumed_units: Mapped[int] = mapped_column(Integer, default=0)
    reserved_units: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class UsageLedger(Base):
    __tablename__ = "usage_ledgers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    credential_ref_id: Mapped[str | None] = mapped_column(
        ForeignKey("credential_refs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    operation: Mapped[str] = mapped_column(String(50), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(30), index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    quota_units: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_microusd: Mapped[int] = mapped_column(Integer, default=0)
    pricing_configured: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="settled", index=True)
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CostAuthorization(Base):
    __tablename__ = "cost_authorizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    credential_ref_id: Mapped[str | None] = mapped_column(
        ForeignKey("credential_refs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    operation: Mapped[str] = mapped_column(String(50), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(30))
    estimated_input_tokens: Mapped[int] = mapped_column(Integer)
    estimated_output_tokens: Mapped[int] = mapped_column(Integer)
    estimated_quota_units: Mapped[int] = mapped_column(Integer)
    estimated_cost_microusd: Mapped[int] = mapped_column(Integer)
    pricing_configured: Mapped[bool] = mapped_column(default=False)
    requires_confirmation: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PreviewAcceptance(Base):
    __tablename__ = "preview_acceptances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    preview_id: Mapped[str] = mapped_column(
        ForeignKey("previews.id", ondelete="CASCADE"), unique=True, index=True
    )
    code_version_id: Mapped[str] = mapped_column(
        ForeignKey("code_versions.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(20), default="accepted")
    checklist_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeploymentAuthorization(Base):
    __tablename__ = "deployment_authorizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    actor_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    credential_ref_id: Mapped[str] = mapped_column(
        ForeignKey("credential_refs.id", ondelete="RESTRICT"), index=True
    )
    action: Mapped[str] = mapped_column(String(30), index=True)
    target_deployment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    provider: Mapped[str] = mapped_column(String(40))
    region: Mapped[str] = mapped_column(String(60))
    environment: Mapped[str] = mapped_column(String(30), default="production")
    permission_scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    estimated_cost_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (UniqueConstraint("project_id", "revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    preview_id: Mapped[str] = mapped_column(
        ForeignKey("previews.id", ondelete="RESTRICT"), index=True
    )
    code_version_id: Mapped[str] = mapped_column(
        ForeignKey("code_versions.id", ondelete="RESTRICT"), index=True
    )
    credential_ref_id: Mapped[str] = mapped_column(
        ForeignKey("credential_refs.id", ondelete="RESTRICT"), index=True
    )
    authorization_id: Mapped[str] = mapped_column(
        ForeignKey("deployment_authorizations.id", ondelete="RESTRICT"), unique=True, index=True
    )
    previous_deployment_id: Mapped[str | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20), default="deploy")
    provider: Mapped[str] = mapped_column(String(40))
    region: Mapped[str] = mapped_column(String(60))
    environment: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    provider_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    deployment_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    checkpoint_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeploymentEvent(Base):
    __tablename__ = "deployment_events"
    __table_args__ = (UniqueConstraint("deployment_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(240))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeliveryPackage(Base):
    __tablename__ = "delivery_packages"
    __table_args__ = (UniqueConstraint("project_id", "revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    deployment_id: Mapped[str] = mapped_column(
        ForeignKey("deployments.id", ondelete="RESTRICT"), index=True
    )
    code_version_id: Mapped[str] = mapped_column(
        ForeignKey("code_versions.id", ondelete="RESTRICT"), index=True
    )
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="ready", index=True)
    storage_path: Mapped[str] = mapped_column(String(240), unique=True)
    filename: Mapped[str] = mapped_column(String(180))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GithubSync(Base):
    __tablename__ = "github_syncs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    delivery_package_id: Mapped[str] = mapped_column(
        ForeignKey("delivery_packages.id", ondelete="CASCADE"), index=True
    )
    repository_full_name: Mapped[str] = mapped_column(String(200))
    branch: Mapped[str] = mapped_column(String(120), default="main")
    status: Mapped[str] = mapped_column(String(20), index=True)
    provider_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    repository_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class BetaInvite(Base):
    __tablename__ = "beta_invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class RateLimitEvent(Base):
    __tablename__ = "rate_limit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key_hash: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class BackupRecord(Base):
    __tablename__ = "backup_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    mode: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), index=True)
    storage_ref: Mapped[str] = mapped_column(String(300), unique=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
