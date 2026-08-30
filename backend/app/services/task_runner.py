from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import ApiError
from app.models import (
    Artifact,
    CodeFile,
    CodeVersion,
    CredentialRef,
    DevelopmentWorkspace,
    Preview,
    ProductChangeRequest,
    Project,
    Task,
    TaskEvent,
    ToolExecution,
)
from app.models.enums import ArtifactType, EventType, ProjectStage, TaskStatus
from app.schemas.contracts import FailureReportContent, PrdContent, PreviewConfig, SolutionContent
from app.services.credentials import SecretVault, provider_for_credential, record_usage
from app.services.development import (
    build_product_context,
    ensure_workspace_and_run,
    finish_tool,
    run_for_task,
    start_tool,
)
from app.services.development_runtime import (
    ControlledCodingError,
    file_sha256,
    materialize_bundle,
)
from app.services.providers import AIProvider, build_code_bundle_with_retry
from app.services.quality_runtime import GeneratedPreviewManager
from app.services.quality_workflow import QualityGateError, execute_quality_and_preview
from app.services.workflow import latest_artifact, next_artifact_version, transition

logger = logging.getLogger(__name__)

CHECKPOINT_ORDER = {
    "accepted": 0,
    "plan_validated": 1,
    "context_loaded": 2,
    "template_generated": 3,
    "files_written": 4,
    "code_committed": 5,
    "contract_validated": 6,
    "quality_passed": 7,
    "preview_ready": 8,
}
LEGACY_CHECKPOINT_ALIASES = {
    "schema_tested": "contract_validated",
    "template_generated": "plan_validated",
}
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class ControlledBuildError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def checkpoint_rank(checkpoint: dict[str, Any]) -> int:
    step = str(checkpoint.get("last_completed_step", "accepted"))
    step = LEGACY_CHECKPOINT_ALIASES.get(step, step)
    return CHECKPOINT_ORDER.get(step, 0)


def _git_command(
    directory: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_AUTHOR_NAME": "AI Product Factory",
        "GIT_AUTHOR_EMAIL": "product-factory@localhost",
        "GIT_COMMITTER_NAME": "AI Product Factory",
        "GIT_COMMITTER_EMAIL": "product-factory@localhost",
    }
    try:
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *args],
            cwd=directory,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError as exc:
        raise ControlledBuildError("GIT_UNAVAILABLE") from exc
    except subprocess.TimeoutExpired as exc:
        raise ControlledBuildError("GIT_TIMEOUT") from exc
    if check and result.returncode != 0:
        raise ControlledBuildError("GIT_COMMIT_FAILED")
    return result


def commit_controlled_manifest(directory: Path) -> str:
    """Create or reuse a real Git commit without invoking a shell or global config."""

    _git_command(directory, "init", "--quiet")
    _git_command(directory, "add", "--", "manifest.json")
    head = _git_command(directory, "rev-parse", "--verify", "HEAD", check=False)
    staged = _git_command(directory, "diff", "--cached", "--quiet", check=False)
    if staged.returncode not in {0, 1}:
        raise ControlledBuildError("GIT_COMMIT_FAILED")
    if head.returncode != 0 or staged.returncode == 1:
        _git_command(
            directory,
            "-c",
            "user.name=AI Product Factory",
            "-c",
            "user.email=product-factory@localhost",
            "commit",
            "--quiet",
            "--no-gpg-sign",
            "-m",
            "Generate controlled preview manifest",
        )
    revision = _git_command(directory, "rev-parse", "HEAD").stdout.strip().lower()
    if not GIT_SHA_PATTERN.fullmatch(revision):
        raise ControlledBuildError("GIT_INVALID_REVISION")
    return revision


def safe_path(root: Path, *parts: str) -> Path:
    root = root.resolve()
    candidate = root.joinpath(*parts).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("generated path escaped workspace root") from exc
    return candidate


def append_task_event(
    db: Session,
    task: Task,
    event_type: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> TaskEvent:
    sequence = (
        int(
            db.scalar(select(func.max(TaskEvent.sequence)).where(TaskEvent.task_id == task.id)) or 0
        )
        + 1
    )
    event = TaskEvent(
        task_id=task.id,
        sequence=sequence,
        type=event_type,
        message=message,
        payload_json=payload or {},
    )
    db.add(event)
    return event


def start_development_task(
    db: Session,
    *,
    project: Project,
    trace_id: str,
    settings: Settings,
    ui_style_key: str = "pirsch-paper",
) -> tuple[Task, bool]:
    if project.stage == ProjectStage.PREVIEW_REVIEW.value:
        latest = db.scalar(
            select(Task)
            .where(Task.project_id == project.id, Task.status == TaskStatus.SUCCEEDED.value)
            .order_by(Task.created_at.desc())
            .limit(1)
        )
        latest_style = str(
            latest.checkpoint_json.get("ui_style_key") or "pirsch-paper"
        ) if latest else None
        if latest and latest_style == ui_style_key:
            return latest, False
        transition(project, ProjectStage.DEVELOPMENT.value)
        project.development_revision += 1
    elif project.stage != ProjectStage.DEVELOPMENT.value:
        raise ApiError("INVALID_PROJECT_STAGE", "请先确认当前方案，再启动开发。", 409)

    key = f"development:{project.id}:{project.development_revision}"
    existing = db.scalar(select(Task).where(Task.idempotency_key == key))
    if existing:
        return existing, False

    solution = latest_artifact(db, project.id, ArtifactType.SOLUTION.value)
    if not solution or solution.status != "confirmed":
        raise ApiError("SOLUTION_NOT_CONFIRMED", "当前方案尚未确认，不能启动开发。", 409)

    change_request = latest_artifact(db, project.id, ArtifactType.CHANGE_REQUEST.value)
    checkpoint: dict[str, Any] = {
        "workflow_key": key,
        "last_completed_step": "accepted",
        "solution_artifact_id": solution.id,
        "ui_style_key": ui_style_key,
    }
    if change_request:
        checkpoint["change_request_artifact_id"] = change_request.id

    task = Task(
        project_id=project.id,
        idempotency_key=key,
        stage=ProjectStage.DEVELOPMENT.value,
        status=TaskStatus.QUEUED.value,
        progress=0,
        attempts=0,
        max_attempts=settings.task_max_attempts,
        budget_json={
            "max_steps": 10,
            "executor": "controlled_code_bundle_v1",
            "max_files": settings.coding_max_files,
            "max_total_bytes": settings.coding_max_total_bytes,
            "max_repairs": settings.quality_max_repairs,
        },
        checkpoint_json=checkpoint,
        trace_id=trace_id,
    )
    db.add(task)
    db.flush()
    _workspace, run = ensure_workspace_and_run(
        db,
        project=project,
        task=task,
        solution_artifact_id=solution.id,
        settings=settings,
    )
    task.checkpoint_json = {**task.checkpoint_json, "development_run_id": run.id}
    append_task_event(
        db,
        task,
        EventType.PROGRESS.value,
        "开发任务已受理。",
        {"progress": 0, "checkpoint": "accepted"},
    )
    return task, True


def retry_failed_task(
    db: Session,
    *,
    failed_task: Task,
    project: Project,
    trace_id: str,
    settings: Settings,
) -> tuple[Task, bool]:
    key = f"retry:{failed_task.id}"
    existing = db.scalar(select(Task).where(Task.idempotency_key == key))
    if existing:
        return existing, False
    if failed_task.status != TaskStatus.FAILED.value:
        raise ApiError("TASK_NOT_RETRYABLE", "只有已失败的任务可以手动恢复。", 409)
    if project.stage != ProjectStage.PAUSED.value:
        raise ApiError("INVALID_PROJECT_STAGE", "项目当前不处于可恢复的暂停状态。", 409)
    latest_task = db.scalar(
        select(Task)
        .where(Task.project_id == project.id)
        .order_by(Task.created_at.desc(), Task.id.desc())
        .limit(1)
    )
    if not latest_task or latest_task.id != failed_task.id:
        raise ApiError("TASK_NOT_LATEST", "只能恢复当前项目最后一个失败任务。", 409)

    source_checkpoint = dict(failed_task.checkpoint_json)
    failure_reports = list(
        db.scalars(
            select(Artifact)
            .where(
                Artifact.project_id == project.id,
                Artifact.type == ArtifactType.FAILURE_REPORT.value,
            )
            .order_by(Artifact.version.desc())
        )
    )
    failure_report = next(
        (
            report
            for report in failure_reports
            if report.content_json.get("task_id") == failed_task.id
        ),
        None,
    )
    source_checkpoint.pop("code_version_id", None)
    source_checkpoint.pop("preview_id", None)
    source_checkpoint.update(
        {
            "workflow_key": key,
            "resumed_from_task_id": failed_task.id,
            "failure_report_id": failure_report.id if failure_report else None,
        }
    )
    project.development_revision += 1
    transition(project, ProjectStage.DEVELOPMENT.value)
    task = Task(
        project_id=project.id,
        idempotency_key=key,
        stage=ProjectStage.DEVELOPMENT.value,
        status=TaskStatus.QUEUED.value,
        progress=failed_task.progress,
        attempts=0,
        max_attempts=settings.task_max_attempts,
        budget_json={
            "max_steps": 10,
            "executor": "controlled_code_bundle_v1",
            "max_files": settings.coding_max_files,
            "max_total_bytes": settings.coding_max_total_bytes,
            "max_repairs": settings.quality_max_repairs,
        },
        checkpoint_json=source_checkpoint,
        trace_id=trace_id,
    )
    db.add(task)
    db.flush()
    source_run = run_for_task(db, failed_task.id)
    solution_id = str(source_checkpoint.get("solution_artifact_id") or "")
    if not solution_id:
        raise ApiError("DEVELOPMENT_CONTEXT_MISSING", "恢复任务缺少已确认方案。", 409)
    _workspace, run = ensure_workspace_and_run(
        db,
        project=project,
        task=task,
        solution_artifact_id=solution_id,
        settings=settings,
        resumed_from_run_id=source_run.id if source_run else None,
    )
    if source_run:
        run.context_json = dict(source_run.context_json)
        run.provider = source_run.provider
        run.model = source_run.model
        run.provider_verification = source_run.provider_verification
    task.checkpoint_json = {**task.checkpoint_json, "development_run_id": run.id}
    append_task_event(
        db,
        task,
        EventType.RETRY.value,
        "已创建新的恢复任务，将从失败任务的最后检查点继续。",
        {
            "progress": failed_task.progress,
            "checkpoint": source_checkpoint.get("last_completed_step"),
            "resumed_from_task_id": failed_task.id,
            "failure_report_id": failure_report.id if failure_report else None,
        },
    )
    return task, True


class PersistentTaskRunner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        provider: AIProvider,
        preview_manager: GeneratedPreviewManager,
        secret_vault: SecretVault,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.provider = provider
        self.preview_manager = preview_manager
        self.secret_vault = secret_vault
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="product-factory-task")
        self._lock = threading.Lock()
        self._scheduled: set[str] = set()

    def recover(self) -> None:
        task_ids: list[str] = []
        with self.session_factory() as db:
            interrupted = list(
                db.scalars(select(Task).where(Task.status == TaskStatus.RUNNING.value))
            )
            for task in interrupted:
                task.status = TaskStatus.QUEUED.value
                task.attempts = max(task.attempts - 1, 0)
                append_task_event(
                    db,
                    task,
                    EventType.RETRY.value,
                    "服务恢复后从最后检查点继续。",
                    {"checkpoint": task.checkpoint_json.get("last_completed_step")},
                )
            db.flush()
            queued = list(db.scalars(select(Task).where(Task.status == TaskStatus.QUEUED.value)))
            for task in queued:
                if run_for_task(db, task.id):
                    continue
                project = db.get(Project, task.project_id)
                solution_id = str(task.checkpoint_json.get("solution_artifact_id") or "")
                if not project or not solution_id:
                    continue
                _workspace, run = ensure_workspace_and_run(
                    db,
                    project=project,
                    task=task,
                    solution_artifact_id=solution_id,
                    settings=self.settings,
                )
                task.checkpoint_json = {
                    **task.checkpoint_json,
                    "development_run_id": run.id,
                }
            task_ids = [task.id for task in queued]
            db.commit()
        for task_id in task_ids:
            self.enqueue(task_id)

    def enqueue(self, task_id: str) -> None:
        with self._lock:
            if task_id in self._scheduled:
                return
            self._scheduled.add(task_id)
        future = self.executor.submit(self._run, task_id)
        future.add_done_callback(lambda completed, value=task_id: self._finish(value, completed))

    def _finish(self, task_id: str, future: Future[None]) -> None:
        with self._lock:
            self._scheduled.discard(task_id)
        error = future.exception()
        if error:
            logger.error(
                "background task crashed task_id=%s error_type=%s", task_id, type(error).__name__
            )

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)

    def _run(self, task_id: str) -> None:
        while True:
            with self.session_factory() as db:
                task = db.get(Task, task_id)
                if not task or task.status in {TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value}:
                    return
                task.status = TaskStatus.RUNNING.value
                task.attempts += 1
                development_run = run_for_task(db, task.id)
                if development_run:
                    development_run.status = "running"
                    development_run.error_code = None
                    workspace = db.get(DevelopmentWorkspace, development_run.workspace_id)
                    if workspace:
                        workspace.status = "busy"
                append_task_event(
                    db,
                    task,
                    EventType.PROGRESS.value,
                    f"开始第 {task.attempts} 次受控构建。",
                    {"progress": max(task.progress, 5), "attempt": task.attempts},
                )
                task.progress = max(task.progress, 5)
                db.commit()

            try:
                self._perform(task_id)
                return
            except Exception as exc:  # noqa: BLE001 - outer boundary persists every task failure
                with self.session_factory() as db:
                    task = db.get(Task, task_id)
                    if not task:
                        return
                    if task.attempts < task.max_attempts and not isinstance(
                        exc, QualityGateError
                    ):
                        task.status = TaskStatus.QUEUED.value
                        append_task_event(
                            db,
                            task,
                            EventType.RETRY.value,
                            "本次受控构建未完成，系统将从最后检查点重试。",
                            {"attempt": task.attempts, "checkpoint": task.checkpoint_json},
                        )
                        db.commit()
                        continue

                    task.status = TaskStatus.FAILED.value
                    task.error_code = (
                        exc.code
                        if isinstance(
                            exc,
                            (
                                ControlledBuildError,
                                ControlledCodingError,
                                QualityGateError,
                                ApiError,
                            ),
                        )
                        else "CONTROLLED_BUILD_FAILED"
                    )
                    development_run = run_for_task(db, task.id)
                    if development_run:
                        development_run.status = "failed"
                        development_run.error_code = task.error_code
                        development_run.completed_at = datetime.now(UTC)
                        workspace = db.get(
                            DevelopmentWorkspace, development_run.workspace_id
                        )
                        if workspace:
                            workspace.status = "paused"
                    project = db.get(Project, task.project_id)
                    if project and project.stage == ProjectStage.DEVELOPMENT.value:
                        transition(project, ProjectStage.PAUSED.value)
                    failure_report = Artifact(
                        project_id=task.project_id,
                        type=ArtifactType.FAILURE_REPORT.value,
                        version=next_artifact_version(
                            db, task.project_id, ArtifactType.FAILURE_REPORT.value
                        ),
                        status="confirmed",
                        content_json=FailureReportContent(
                            title="受控构建失败报告",
                            task_id=task.id,
                            failed_stage=task.stage,
                            attempts=task.attempts,
                            error_code=task.error_code,
                            last_checkpoint=dict(task.checkpoint_json),
                            attempted_recovery=[
                                f"已执行 {task.attempts} 次受控构建",
                                "每次均从持久化检查点继续",
                            ],
                            recovery="修复后端配置或受控契约问题后，将项目恢复到开发阶段并重新运行。",
                        ).model_dump(mode="json"),
                    )
                    db.add(failure_report)
                    if project:
                        project.current_artifact_version = max(
                            project.current_artifact_version, failure_report.version
                        )
                    db.flush()
                    append_task_event(
                        db,
                        task,
                        EventType.ERROR.value,
                        "构建在重试上限内仍未通过。最后检查点已保存，可排查后恢复。",
                        {
                            "error_code": task.error_code,
                            "checkpoint": task.checkpoint_json,
                            "failure_report_id": failure_report.id,
                            "recovery": "修复配置后重新进入开发阶段。",
                        },
                    )
                    db.commit()
                logger.warning(
                    "controlled build failed task_id=%s error_type=%s",
                    task_id,
                    type(exc).__name__,
                )
                return

    def _checkpoint(self, task_id: str, progress: int, step: str, message: str) -> bool:
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if not task:
                raise RuntimeError("task disappeared")
            checkpoint = dict(task.checkpoint_json)
            if checkpoint_rank(checkpoint) >= CHECKPOINT_ORDER[step]:
                return False
            task.progress = max(task.progress, progress)
            checkpoint["last_completed_step"] = step
            task.checkpoint_json = checkpoint
            append_task_event(
                db,
                task,
                EventType.PROGRESS.value,
                message,
                {"progress": task.progress, "checkpoint": step},
            )
            db.commit()
            return True

    def _step_pending(self, task_id: str, step: str) -> bool:
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if not task:
                raise RuntimeError("task disappeared")
            return checkpoint_rank(task.checkpoint_json) < CHECKPOINT_ORDER[step]

    def _provider_for_task(self, task_id: str) -> tuple[AIProvider, str | None]:
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if not task:
                raise RuntimeError("task disappeared")
            credential_id = task.checkpoint_json.get("credential_ref_id")
            if not credential_id:
                return self.provider, None
            project = db.get(Project, task.project_id)
            if not project:
                raise RuntimeError("development project disappeared")
            provider, credential = provider_for_credential(
                db,
                settings=self.settings,
                vault=self.secret_vault,
                owner_id=project.owner_id,
                credential_id=str(credential_id),
                project_id=project.id,
            )
            if credential.scope not in {"development", "both"}:
                raise ApiError("CREDENTIAL_SCOPE_DENIED", "这个模型 Key 未授权用于开发。", 403)
            if credential.status != "verified":
                raise ApiError("CREDENTIAL_NOT_VERIFIED", "模型 Key 尚未通过验证。", 409)
            db.commit()
            return provider, credential.id

    def _perform(self, task_id: str) -> None:
        provider, credential_id = self._provider_for_task(task_id)
        self._checkpoint(task_id, 12, "plan_validated", "已锁定第四阶段开发、测试与修复预算。")

        if self._step_pending(task_id, "context_loaded"):
            with self.session_factory() as db:
                task = db.get(Task, task_id)
                if not task:
                    raise RuntimeError("task disappeared")
                project = db.get(Project, task.project_id)
                run = run_for_task(db, task.id)
                if not project or not run:
                    raise RuntimeError("development context disappeared")
                solution = db.get(Artifact, run.solution_artifact_id)
                prd = latest_artifact(db, project.id, ArtifactType.PRD.value)
                if (
                    not solution
                    or solution.project_id != project.id
                    or solution.type != ArtifactType.SOLUTION.value
                    or not prd
                    or prd.status != "confirmed"
                ):
                    raise ControlledCodingError(
                        "DEVELOPMENT_CONTEXT_INVALID", "已确认的 PRD 或方案不可用。"
                    )
                PrdContent.model_validate(prd.content_json)
                SolutionContent.model_validate(solution.content_json)
                tool = start_tool(
                    db,
                    run=run,
                    tool_name="context_loader",
                    side_effect="read_only",
                    input_summary={"project_id": project.id},
                )
                product_context = build_product_context(db, project.id)
                product_context["ui_style_key"] = str(
                    task.checkpoint_json.get("ui_style_key") or "pirsch-paper"
                )
                legacy_change_id = task.checkpoint_json.get("change_request_artifact_id")
                legacy_change = db.get(Artifact, legacy_change_id) if legacy_change_id else None
                if legacy_change and legacy_change.project_id == project.id:
                    product_context["confirmed_changes"].append(
                        {
                            "change_request_id": legacy_change.id,
                            "source_type": "preview_feedback",
                            "product_request": legacy_change.content_json.get("feedback", ""),
                            "scope_classification": "in_scope",
                        }
                    )
                run.context_json = {
                    "prd_artifact_id": prd.id,
                    "solution_artifact_id": solution.id,
                    "product_context": product_context,
                }
                run.current_step = "context_loaded"
                finish_tool(
                    tool,
                    output_summary={
                        "confirmed_prd": True,
                        "confirmed_solution": True,
                        "decision_count": len(product_context["confirmed_decisions"]),
                        "change_count": len(product_context["confirmed_changes"]),
                    },
                )
                db.commit()
            self._checkpoint(task_id, 25, "context_loaded", "已读取确认内容和产品决策。")

        if self._step_pending(task_id, "code_committed"):
            if self.settings.task_force_failure:
                raise RuntimeError("forced controlled failure")

            with self.session_factory() as db:
                task = db.get(Task, task_id)
                if not task:
                    raise RuntimeError("task disappeared")
                project = db.get(Project, task.project_id)
                run = run_for_task(db, task.id)
                if not project or not run:
                    raise RuntimeError("development context disappeared")
                prd = db.get(Artifact, run.context_json.get("prd_artifact_id"))
                solution = db.get(Artifact, run.solution_artifact_id)
                if not prd or not solution:
                    raise RuntimeError("confirmed artifacts disappeared")
                prd_content = PrdContent.model_validate(prd.content_json)
                solution_content = SolutionContent.model_validate(solution.content_json)
                product_context = dict(run.context_json.get("product_context") or {})
                provider_tool = start_tool(
                    db,
                    run=run,
                    tool_name="coding_provider",
                    side_effect="model_call",
                    input_summary={
                        "project_id": project.id,
                        "prd_artifact_id": prd.id,
                        "solution_artifact_id": solution.id,
                    },
                )
                provider_tool_id = provider_tool.id
                project_name = project.name
                project_idea = project.idea
                project_id = project.id
                db.commit()

            try:
                provider_call = build_code_bundle_with_retry(
                    provider,
                    project_name=project_name,
                    idea=project_idea,
                    prd=prd_content,
                    solution=solution_content,
                    product_context=product_context,
                    max_attempts=self.settings.ai_max_attempts,
                )
            except Exception as exc:
                with self.session_factory() as db:
                    tool = db.get(ToolExecution, provider_tool_id)
                    if tool:
                        finish_tool(
                            tool,
                            output_summary={"result": "rejected"},
                            error_code=getattr(exc, "code", "CODING_PROVIDER_FAILED"),
                        )
                        db.commit()
                raise

            with self.session_factory() as db:
                task = db.get(Task, task_id)
                run = run_for_task(db, task_id)
                provider_tool = db.get(ToolExecution, provider_tool_id)
                if not task or not run or not provider_tool:
                    raise RuntimeError("development run disappeared")
                run.provider = provider.name
                run.model = provider.model
                run.provider_verification = provider.verification
                run.usage_json = dict(provider_call.usage)
                project = db.get(Project, task.project_id)
                credential = db.get(CredentialRef, credential_id) if credential_id else None
                if not project:
                    raise RuntimeError("development project disappeared")
                record_usage(
                    db,
                    settings=self.settings,
                    owner_id=project.owner_id,
                    project_id=project.id,
                    task_id=task.id,
                    credential=credential,
                    operation="development",
                    provider=provider.name,
                    model=provider.model,
                    usage=provider_call.usage,
                    trace_id=task.trace_id,
                )
                run.current_step = "code_bundle_generated"
                finish_tool(
                    provider_tool,
                    output_summary={
                        "file_count": len(provider_call.content.files),
                        "provider_verification": provider.verification,
                        "prompt_version": provider_call.usage.get("prompt_version"),
                    },
                )
                writer_tool = start_tool(
                    db,
                    run=run,
                    tool_name="workspace_writer",
                    side_effect="filesystem_write",
                    input_summary={
                        "file_count": len(provider_call.content.files),
                        "workspace_id": run.workspace_id,
                    },
                )
                writer_tool_id = writer_tool.id
                current_version = int(
                    db.scalar(
                        select(func.max(CodeVersion.version)).where(
                            CodeVersion.project_id == project_id
                        )
                    )
                    or 0
                )
                version = current_version + 1
                db.commit()

            try:
                materialized = materialize_bundle(
                    settings=self.settings,
                    project_id=project_id,
                    bundle=provider_call.content,
                    commit_message=f"Generate code version {version}",
                )
            except Exception as exc:
                with self.session_factory() as db:
                    tool = db.get(ToolExecution, writer_tool_id)
                    if tool:
                        finish_tool(
                            tool,
                            output_summary={"result": "write_blocked"},
                            error_code=getattr(exc, "code", "WORKSPACE_WRITE_FAILED"),
                        )
                        db.commit()
                raise

            with self.session_factory() as db:
                task = db.get(Task, task_id)
                project = db.get(Project, project_id)
                run = run_for_task(db, task_id)
                writer_tool = db.get(ToolExecution, writer_tool_id)
                if not task or not project or not run or not writer_tool:
                    raise RuntimeError("development run disappeared")
                finish_tool(
                    writer_tool,
                    output_summary={
                        "file_count": len(materialized.files),
                        "size_bytes": materialized.total_bytes,
                    },
                )
                git_tool = start_tool(
                    db,
                    run=run,
                    tool_name="git_checkpoint",
                    side_effect="git_commit",
                    input_summary={"version": version},
                )
                legacy_change_id = task.checkpoint_json.get("change_request_artifact_id")
                legacy_change = db.get(Artifact, legacy_change_id) if legacy_change_id else None
                config = PreviewConfig(
                    title=prd_content.title,
                    description=prd_content.summary[:500],
                    input_label="记录本次页面验收反馈",
                    input_placeholder="例如：计时开始、暂停、继续和重置均可使用。",
                    submit_label="保存验收记录",
                    output_title="验收记录",
                    template=(
                        "controlled_html_webapp_v1"
                        if provider_call.content.template == "controlled_html_webapp_v1"
                        else "controlled_text_agent_v1"
                    ),
                )
                manifest = {
                    "template": config.template,
                    "code_template": provider_call.content.template,
                    "template_version": 1,
                    "project_id": project.id,
                    "development_run_id": run.id,
                    "solution_artifact_id": run.solution_artifact_id,
                    "change_request_artifact_id": legacy_change.id if legacy_change else None,
                    "change_request": legacy_change.content_json if legacy_change else None,
                    "product_context": run.context_json.get("product_context", {}),
                    "resumed_from_task_id": task.checkpoint_json.get("resumed_from_task_id"),
                    "generated_files": [item.path for item in materialized.files],
                    "permissions": {
                        "shell": "allowlisted_quality_commands_only",
                        "network": "configured_model_endpoint_only",
                        "filesystem": "assigned_project_workspace_only",
                    },
                    "provider": provider.name,
                    "model": provider.model,
                    "provider_verification": provider.verification,
                    "preview_config": config.model_dump(mode="json"),
                }
                code_version = CodeVersion(
                    project_id=project.id,
                    version=version,
                    commit_ref=materialized.commit_ref,
                    test_status="testing",
                    manifest_json=manifest,
                )
                db.add(code_version)
                db.flush()
                for item in materialized.files:
                    db.add(
                        CodeFile(
                            code_version_id=code_version.id,
                            path=item.path,
                            language=item.language,
                            product_purpose=item.product_purpose,
                            sha256=file_sha256(item.content),
                            size_bytes=len(item.content.encode("utf-8")),
                        )
                    )
                workspace = db.get(DevelopmentWorkspace, run.workspace_id)
                if workspace:
                    workspace.current_commit_ref = materialized.commit_ref
                    workspace.file_count = len(materialized.files)
                    workspace.size_bytes = materialized.total_bytes
                run.code_version_id = code_version.id
                run.current_step = "code_committed"
                for change in db.scalars(
                    select(ProductChangeRequest).where(
                        ProductChangeRequest.project_id == project.id,
                        ProductChangeRequest.status.in_(["confirmed", "queued"]),
                    )
                ):
                    change.status = "applied"
                    change.base_code_version_id = code_version.id
                finish_tool(
                    git_tool,
                    output_summary={
                        "commit_ref": materialized.commit_ref,
                        "changed_files": materialized.changed_files,
                    },
                )
                task.progress = max(task.progress, 70)
                task.checkpoint_json = {
                    **task.checkpoint_json,
                    "last_completed_step": "code_committed",
                    "code_version_id": code_version.id,
                    "commit_ref": materialized.commit_ref,
                }
                append_task_event(
                    db,
                    task,
                    EventType.PROGRESS.value,
                    "已在隔离工作区生成真实代码文件并保存 Git 版本。",
                    {
                        "progress": task.progress,
                        "checkpoint": "code_committed",
                        "code_version": version,
                        "file_count": len(materialized.files),
                    },
                )
                db.commit()

        self._checkpoint(task_id, 76, "contract_validated", "文件范围和代码契约校验通过。")

        if self._step_pending(task_id, "quality_passed"):
            code_version_id, preview_id = execute_quality_and_preview(
                self.session_factory,
                self.settings,
                provider,
                self.preview_manager,
                task_id=task_id,
            )
            with self.session_factory() as db:
                task = db.get(Task, task_id)
                if not task:
                    raise RuntimeError("task disappeared")
                task.progress = max(task.progress, 95)
                task.checkpoint_json = {
                    **task.checkpoint_json,
                    "last_completed_step": "quality_passed",
                    "code_version_id": code_version_id,
                    "preview_id": preview_id,
                }
                append_task_event(
                    db,
                    task,
                    EventType.PROGRESS.value,
                    "编译、自动化测试和真实生成应用冒烟均已通过。",
                    {
                        "progress": task.progress,
                        "checkpoint": "quality_passed",
                        "code_version_id": code_version_id,
                        "preview_id": preview_id,
                    },
                )
                db.commit()

        if not self._step_pending(task_id, "preview_ready"):
            return
        with self.session_factory() as db:
            task = db.get(Task, task_id)
            if not task:
                raise RuntimeError("task disappeared")
            project = db.get(Project, task.project_id)
            run = run_for_task(db, task.id)
            code_version_id = task.checkpoint_json.get("code_version_id")
            code_version = db.get(CodeVersion, code_version_id) if code_version_id else None
            if not project or not run or not code_version:
                raise RuntimeError("committed code version disappeared")
            preview_id = task.checkpoint_json.get("preview_id")
            preview = db.get(Preview, preview_id) if preview_id else None
            if not preview or preview.status != "ready":
                raise QualityGateError(
                    "PREVIEW_RUNTIME_NOT_READY",
                    {"preview_id": preview_id, "code_version_id": code_version.id},
                )
            task.progress = 100
            task.status = TaskStatus.SUCCEEDED.value
            task.error_code = None
            task.checkpoint_json = {
                **task.checkpoint_json,
                "last_completed_step": "preview_ready",
                "preview_id": preview.id,
            }
            run.status = "succeeded"
            run.current_step = "preview_ready"
            run.error_code = None
            run.completed_at = datetime.now(UTC)
            workspace = db.get(DevelopmentWorkspace, run.workspace_id)
            if workspace:
                workspace.status = "ready"
            transition(project, ProjectStage.PREVIEW_REVIEW.value)
            append_task_event(
                db,
                task,
                EventType.DONE.value,
                "第四阶段质量门已通过；真实生成应用临时预览已准备好。",
                {
                    "progress": 100,
                    "code_version": code_version.version,
                    "preview_token": preview.preview_token,
                    "test_status": "quality_passed",
                    "development_run_id": run.id,
                },
            )
            db.commit()
