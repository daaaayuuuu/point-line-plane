from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError, not_found
from app.models import (
    CodeFile,
    DevelopmentRun,
    DevelopmentWorkspace,
    PreviewRuntime,
    ProductChangeRequest,
    ProductDecision,
    ProductGraph,
    Project,
    QualityRun,
    RepairAttempt,
    Task,
    ToolExecution,
)
from app.models.enums import (
    DevelopmentRunStatus,
    DevelopmentWorkspaceStatus,
    ToolExecutionStatus,
)
from app.schemas.contracts import (
    CodeFileMetadataResponse,
    DevelopmentRunResponse,
    DevelopmentWorkspaceResponse,
    PreviewRuntimeResponse,
    QualityRunResponse,
    RepairAttemptResponse,
    ToolExecutionResponse,
)


def default_development_plan() -> dict[str, Any]:
    return {
        "version": "m1d-quality-preview-plan-v1",
        "steps": [
            {
                "key": "load_confirmed_context",
                "product_language": "读取已经确认的 PRD、方案和产品决策",
                "technical_action": "context_loader",
            },
            {
                "key": "generate_code_bundle",
                "product_language": "把确认内容和所选 UI 风格生成可操作的 HTML 页面与运行后端",
                "technical_action": "coding_provider",
            },
            {
                "key": "validate_and_write",
                "product_language": "检查文件范围、大小和密钥风险后写入隔离工作区",
                "technical_action": "workspace_writer",
            },
            {
                "key": "git_checkpoint",
                "product_language": "保存一个可以追溯和恢复的代码版本",
                "technical_action": "git_checkpoint",
            },
            {
                "key": "quality_gate",
                "product_language": "运行编译、自动化测试和真实接口冒烟",
                "technical_action": "quality_runner",
            },
            {
                "key": "automatic_repair",
                "product_language": "失败时在预算内生成修复版本并重新测试",
                "technical_action": "repair_provider",
            },
            {
                "key": "runtime_preview",
                "product_language": "启动绑定测试通过版本的真实临时预览",
                "technical_action": "preview_runtime",
            },
        ],
        "not_in_this_stage": [
            "公网预览托管",
            "云部署",
            "额度计费",
        ],
    }


def ensure_workspace_and_run(
    db: Session,
    *,
    project: Project,
    task: Task,
    solution_artifact_id: str,
    settings: Settings,
    resumed_from_run_id: str | None = None,
) -> tuple[DevelopmentWorkspace, DevelopmentRun]:
    workspace = db.scalar(
        select(DevelopmentWorkspace).where(DevelopmentWorkspace.project_id == project.id)
    )
    if not workspace:
        workspace = DevelopmentWorkspace(
            project_id=project.id,
            relative_path=f"{project.id}/repository",
            runtime_type="controlled_code_bundle_v1",
            status=DevelopmentWorkspaceStatus.READY.value,
        )
        db.add(workspace)
        db.flush()

    run = db.scalar(select(DevelopmentRun).where(DevelopmentRun.task_id == task.id))
    if run:
        return workspace, run
    run = DevelopmentRun(
        project_id=project.id,
        workspace_id=workspace.id,
        task_id=task.id,
        solution_artifact_id=solution_artifact_id,
        resumed_from_run_id=resumed_from_run_id,
        idempotency_key=f"coding:{task.id}",
        status=DevelopmentRunStatus.QUEUED.value,
        current_step="accepted",
        plan_json=default_development_plan(),
        budget_json={
            "max_files": settings.coding_max_files,
            "max_file_bytes": settings.coding_max_file_bytes,
            "max_total_bytes": settings.coding_max_total_bytes,
            "network": "configured_model_endpoint_only",
            "shell": "denied",
            "filesystem": "assigned_project_workspace_only",
            "quality_timeout_seconds": settings.quality_command_timeout_seconds,
            "max_repairs": settings.quality_max_repairs,
            "execution_mode": settings.generated_execution_mode,
        },
    )
    db.add(run)
    db.flush()
    return workspace, run


def run_for_task(db: Session, task_id: str) -> DevelopmentRun | None:
    return db.scalar(select(DevelopmentRun).where(DevelopmentRun.task_id == task_id))


def owned_development_run(db: Session, run_id: str, owner_id: str) -> DevelopmentRun:
    run = db.scalar(
        select(DevelopmentRun)
        .join(Project, Project.id == DevelopmentRun.project_id)
        .where(DevelopmentRun.id == run_id, Project.owner_id == owner_id)
    )
    if not run:
        raise not_found("开发运行")
    return run


def owned_workspace(db: Session, project_id: str, owner_id: str) -> DevelopmentWorkspace:
    workspace = db.scalar(
        select(DevelopmentWorkspace)
        .join(Project, Project.id == DevelopmentWorkspace.project_id)
        .where(DevelopmentWorkspace.project_id == project_id, Project.owner_id == owner_id)
    )
    if not workspace:
        raise ApiError("DEVELOPMENT_WORKSPACE_NOT_READY", "项目还没有进入第三阶段自动开发。", 409)
    return workspace


def build_product_context(db: Session, project_id: str) -> dict[str, Any]:
    graph = db.scalar(
        select(ProductGraph)
        .where(ProductGraph.project_id == project_id, ProductGraph.status == "active")
        .order_by(ProductGraph.version.desc())
        .limit(1)
    )
    decisions: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    if graph:
        for decision in db.scalars(
            select(ProductDecision)
            .where(
                ProductDecision.graph_id == graph.id,
                ProductDecision.status == "confirmed",
            )
            .order_by(ProductDecision.created_at)
        ):
            decisions.append(
                {
                    "decision_id": decision.id,
                    "key": decision.key,
                    "selected_option_key": decision.selected_option_key,
                }
            )
        for change in db.scalars(
            select(ProductChangeRequest)
            .where(
                ProductChangeRequest.project_id == project_id,
                ProductChangeRequest.status.in_(["confirmed", "queued"]),
            )
            .order_by(ProductChangeRequest.created_at)
        ):
            changes.append(
                {
                    "change_request_id": change.id,
                    "source_type": change.source_type,
                    "product_request": change.product_request,
                    "scope_classification": change.scope_classification,
                }
            )
    return {
        "graph_id": graph.id if graph else None,
        "graph_version": graph.version if graph else None,
        "confirmed_decisions": decisions,
        "confirmed_changes": changes,
    }


def start_tool(
    db: Session,
    *,
    run: DevelopmentRun,
    tool_name: str,
    side_effect: str,
    input_summary: dict[str, Any],
) -> ToolExecution:
    sequence = int(
        db.scalar(select(func.max(ToolExecution.sequence)).where(ToolExecution.run_id == run.id))
        or 0
    ) + 1
    tool = ToolExecution(
        run_id=run.id,
        sequence=sequence,
        tool_name=tool_name,
        side_effect=side_effect,
        status=ToolExecutionStatus.RUNNING.value,
        input_summary_json=input_summary,
    )
    db.add(tool)
    db.flush()
    return tool


def finish_tool(
    tool: ToolExecution,
    *,
    output_summary: dict[str, Any],
    error_code: str | None = None,
) -> None:
    tool.status = (
        ToolExecutionStatus.FAILED.value if error_code else ToolExecutionStatus.SUCCEEDED.value
    )
    tool.output_summary_json = output_summary
    tool.error_code = error_code
    tool.completed_at = datetime.now(UTC)


def code_file_metadata(item: CodeFile) -> CodeFileMetadataResponse:
    return CodeFileMetadataResponse(
        id=item.id,
        path=item.path,
        language=item.language,
        product_purpose=item.product_purpose,
        sha256=item.sha256,
        size_bytes=item.size_bytes,
        created_at=item.created_at,
    )


def tool_response(item: ToolExecution) -> ToolExecutionResponse:
    return ToolExecutionResponse(
        id=item.id,
        sequence=item.sequence,
        tool_name=item.tool_name,
        side_effect=item.side_effect,
        status=item.status,
        input_summary=item.input_summary_json,
        output_summary=item.output_summary_json,
        error_code=item.error_code,
        started_at=item.started_at,
        completed_at=item.completed_at,
    )


def workspace_response(item: DevelopmentWorkspace) -> DevelopmentWorkspaceResponse:
    return DevelopmentWorkspaceResponse(
        id=item.id,
        project_id=item.project_id,
        runtime_type=item.runtime_type,
        status=item.status,
        current_commit_ref=item.current_commit_ref,
        file_count=item.file_count,
        size_bytes=item.size_bytes,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def development_run_response(db: Session, run: DevelopmentRun) -> DevelopmentRunResponse:
    tools = list(
        db.scalars(
            select(ToolExecution)
            .where(ToolExecution.run_id == run.id)
            .order_by(ToolExecution.sequence)
        )
    )
    files: list[CodeFile] = []
    if run.code_version_id:
        files = list(
            db.scalars(
                select(CodeFile)
                .where(CodeFile.code_version_id == run.code_version_id)
                .order_by(CodeFile.path)
            )
        )
    return DevelopmentRunResponse(
        id=run.id,
        project_id=run.project_id,
        workspace_id=run.workspace_id,
        task_id=run.task_id,
        solution_artifact_id=run.solution_artifact_id,
        code_version_id=run.code_version_id,
        resumed_from_run_id=run.resumed_from_run_id,
        status=run.status,
        current_step=run.current_step,
        provider=run.provider,
        model=run.model,
        provider_verification=run.provider_verification,
        plan=run.plan_json,
        budget=run.budget_json,
        context=run.context_json,
        usage=run.usage_json,
        error_code=run.error_code,
        tools=[tool_response(tool) for tool in tools],
        files=[code_file_metadata(item) for item in files],
        created_at=run.created_at,
        updated_at=run.updated_at,
        completed_at=run.completed_at,
    )


def quality_run_response(item: QualityRun) -> QualityRunResponse:
    return QualityRunResponse(
        id=item.id,
        project_id=item.project_id,
        task_id=item.task_id,
        development_run_id=item.development_run_id,
        code_version_id=item.code_version_id,
        sequence=item.sequence,
        kind=item.kind,
        status=item.status,
        attempt=item.attempt,
        duration_ms=item.duration_ms,
        exit_code=item.exit_code,
        summary=item.summary_json,
        output_excerpt=item.output_excerpt,
        started_at=item.started_at,
        completed_at=item.completed_at,
    )


def repair_attempt_response(item: RepairAttempt) -> RepairAttemptResponse:
    return RepairAttemptResponse(
        id=item.id,
        project_id=item.project_id,
        task_id=item.task_id,
        development_run_id=item.development_run_id,
        attempt=item.attempt,
        status=item.status,
        source_code_version_id=item.source_code_version_id,
        repaired_code_version_id=item.repaired_code_version_id,
        failure_summary=item.failure_summary_json,
        strategy_summary=item.strategy_summary,
        usage=item.usage_json,
        error_code=item.error_code,
        created_at=item.created_at,
        completed_at=item.completed_at,
    )


def preview_runtime_response(
    item: PreviewRuntime,
    *,
    public_base_url: str | None,
) -> PreviewRuntimeResponse:
    return PreviewRuntimeResponse(
        id=item.id,
        preview_id=item.preview_id,
        project_id=item.project_id,
        code_version_id=item.code_version_id,
        runtime_type=item.runtime_type,
        status=item.status,
        base_url=public_base_url,
        health=item.health_json,
        error_code=item.error_code,
        started_at=item.started_at,
        last_health_at=item.last_health_at,
        stopped_at=item.stopped_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
