from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.security import new_preview_token
from app.models import (
    Artifact,
    CodeFile,
    CodeVersion,
    CredentialRef,
    DevelopmentRun,
    DevelopmentWorkspace,
    Preview,
    PreviewRuntime,
    Project,
    QualityRun,
    RepairAttempt,
    Task,
    TaskEvent,
    ToolExecution,
)
from app.models.enums import ArtifactType, EventType
from app.schemas.contracts import PrdContent, PreviewConfig, SolutionContent
from app.services.credentials import record_usage
from app.services.development import finish_tool, run_for_task, start_tool
from app.services.development_runtime import (
    file_sha256,
    materialize_bundle,
    restore_commit,
)
from app.services.providers import AIProvider, build_code_bundle_with_retry
from app.services.quality_runtime import (
    CommandResult,
    GeneratedPreviewManager,
    QualityRuntimeError,
    run_quality_command,
)
from app.services.workflow import latest_artifact


class QualityGateError(RuntimeError):
    def __init__(self, code: str, summary: dict[str, Any]) -> None:
        super().__init__(code)
        self.code = code
        self.summary = summary


def _append_event(
    db: Session,
    task: Task,
    event_type: str,
    message: str,
    payload: dict[str, Any],
) -> None:
    sequence = int(
        db.scalar(select(func.max(TaskEvent.sequence)).where(TaskEvent.task_id == task.id)) or 0
    ) + 1
    db.add(
        TaskEvent(
            task_id=task.id,
            sequence=sequence,
            type=event_type,
            message=message,
            payload_json=payload,
        )
    )


def _quality_sequence(db: Session, task_id: str) -> int:
    return int(
        db.scalar(select(func.max(QualityRun.sequence)).where(QualityRun.task_id == task_id)) or 0
    ) + 1


def _persist_result(
    db: Session,
    *,
    task: Task,
    run: DevelopmentRun,
    code_version: CodeVersion,
    kind: str,
    attempt: int,
    result: CommandResult,
    summary: dict[str, Any] | None = None,
) -> QualityRun:
    item = QualityRun(
        project_id=task.project_id,
        task_id=task.id,
        development_run_id=run.id,
        code_version_id=code_version.id,
        sequence=_quality_sequence(db, task.id),
        kind=kind,
        status=result.status,
        attempt=attempt,
        duration_ms=result.duration_ms,
        exit_code=result.exit_code,
        summary_json=summary or {},
        output_excerpt=result.output_excerpt,
        completed_at=datetime.now(UTC),
    )
    db.add(item)
    return item


def _existing_result(
    db: Session,
    *,
    task_id: str,
    code_version_id: str,
    kind: str,
    attempt: int,
) -> QualityRun | None:
    return db.scalar(
        select(QualityRun).where(
            QualityRun.task_id == task_id,
            QualityRun.code_version_id == code_version_id,
            QualityRun.kind == kind,
            QualityRun.attempt == attempt,
        )
    )


def _run_code_checks(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    task_id: str,
    code_version_id: str,
    attempt: int,
    provider_name: str | None,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    with session_factory() as db:
        run = run_for_task(db, task_id)
        if not run:
            raise QualityGateError("QUALITY_CONTEXT_MISSING", {"task_id": task_id})
        tool = start_tool(
            db,
            run=run,
            tool_name="quality_runner",
            side_effect="allowlisted_process",
            input_summary={"attempt": attempt, "checks": ["compile", "pytest"]},
        )
        tool_id = tool.id
        db.commit()
    for kind in ("compile", "pytest"):
        with session_factory() as db:
            existing = _existing_result(
                db,
                task_id=task_id,
                code_version_id=code_version_id,
                kind=kind,
                attempt=attempt,
            )
            if existing:
                if existing.status != "passed":
                    failures.append(
                        {
                            "kind": kind,
                            "status": existing.status,
                            "output": existing.output_excerpt,
                        }
                    )
                    break
                continue

        if kind == "pytest" and attempt <= settings.quality_force_failures:
            result = CommandResult(
                status="failed",
                exit_code=1,
                duration_ms=1,
                output_excerpt="受控故障注入：用于验证有限修复和版本回退。",
            )
        else:
            result = run_quality_command(
                settings=settings,
                project_id=_task_project_id(session_factory, task_id),
                provider=provider_name,
                kind=kind,
            )
        with session_factory() as db:
            task = db.get(Task, task_id)
            run = run_for_task(db, task_id)
            code_version = db.get(CodeVersion, code_version_id)
            if not task or not run or not code_version:
                raise QualityGateError("QUALITY_CONTEXT_MISSING", {"kind": kind})
            _persist_result(
                db,
                task=task,
                run=run,
                code_version=code_version,
                kind=kind,
                attempt=attempt,
                result=result,
                summary={"command": kind, "allowlisted": True},
            )
            _append_event(
                db,
                task,
                EventType.PROGRESS.value,
                "代码编译检查已完成。" if kind == "compile" else "自动化测试已完成。",
                {
                    "checkpoint": kind,
                    "status": result.status,
                    "attempt": attempt,
                    "code_version_id": code_version.id,
                },
            )
            db.commit()
        if result.status != "passed":
            failures.append(
                {"kind": kind, "status": result.status, "output": result.output_excerpt}
            )
            break
    with session_factory() as db:
        tool = db.get(ToolExecution, tool_id)
        if tool:
            finish_tool(
                tool,
                output_summary={
                    "attempt": attempt,
                    "status": "failed" if failures else "passed",
                    "failed_checks": [item["kind"] for item in failures],
                },
                error_code="QUALITY_CHECK_FAILED" if failures else None,
            )
            db.commit()
    return failures


def _task_project_id(session_factory: sessionmaker[Session], task_id: str) -> str:
    with session_factory() as db:
        task = db.get(Task, task_id)
        if not task:
            raise QualityGateError("QUALITY_CONTEXT_MISSING", {"task_id": task_id})
        return task.project_id


def _next_code_version(db: Session, project_id: str) -> int:
    return int(
        db.scalar(select(func.max(CodeVersion.version)).where(CodeVersion.project_id == project_id))
        or 0
    ) + 1


def _repair_code(
    session_factory: sessionmaker[Session],
    settings: Settings,
    provider: AIProvider,
    *,
    task_id: str,
    source_code_version_id: str,
    attempt: int,
    failures: list[dict[str, Any]],
) -> str:
    with session_factory() as db:
        task = db.get(Task, task_id)
        run = run_for_task(db, task_id)
        source = db.get(CodeVersion, source_code_version_id)
        if not task or not run or not source:
            raise QualityGateError("REPAIR_CONTEXT_MISSING", {"attempt": attempt})
        existing = db.scalar(
            select(RepairAttempt).where(
                RepairAttempt.task_id == task.id,
                RepairAttempt.attempt == attempt,
            )
        )
        if existing and existing.status == "succeeded" and existing.repaired_code_version_id:
            return existing.repaired_code_version_id
        project = db.get(Project, task.project_id)
        prd = latest_artifact(db, task.project_id, ArtifactType.PRD.value)
        solution = db.get(Artifact, run.solution_artifact_id)
        if not project or not prd or not solution:
            raise QualityGateError("REPAIR_CONTEXT_MISSING", {"attempt": attempt})
        repair = existing or RepairAttempt(
            project_id=project.id,
            task_id=task.id,
            development_run_id=run.id,
            attempt=attempt,
            status="running",
            source_code_version_id=source.id,
            failure_summary_json={"checks": failures},
            strategy_summary="根据脱敏测试摘要重新生成受控代码包，然后再次运行全部质量门。",
        )
        if not existing:
            db.add(repair)
        tool = start_tool(
            db,
            run=run,
            tool_name="repair_provider",
            side_effect="model_call",
            input_summary={"attempt": attempt, "failed_checks": [item["kind"] for item in failures]},
        )
        repair_id = repair.id
        tool_id = tool.id
        project_id = project.id
        project_name = project.name
        project_idea = project.idea
        prd_content = PrdContent.model_validate(prd.content_json)
        solution_content = SolutionContent.model_validate(solution.content_json)
        product_context = dict(run.context_json.get("product_context") or {})
        product_context["quality_repair"] = {
            "attempt": attempt,
            "failed_checks": [
                {"kind": item["kind"], "status": item["status"], "output": item["output"][:2000]}
                for item in failures
            ],
        }
        version = _next_code_version(db, project.id)
        db.commit()

    try:
        call = build_code_bundle_with_retry(
            provider,
            project_name=project_name,
            idea=project_idea,
            prd=prd_content,
            solution=solution_content,
            product_context=product_context,
            max_attempts=settings.ai_max_attempts,
        )
        materialized = materialize_bundle(
            settings=settings,
            project_id=project_id,
            bundle=call.content,
            commit_message=f"Automatic repair {attempt} code version {version}",
        )
    except Exception as exc:
        with session_factory() as db:
            repair = db.get(RepairAttempt, repair_id)
            tool = db.get(ToolExecution, tool_id)
            if repair:
                repair.status = "failed"
                repair.error_code = getattr(exc, "code", "AUTO_REPAIR_FAILED")
                repair.completed_at = datetime.now(UTC)
            if tool:
                finish_tool(
                    tool,
                    output_summary={"attempt": attempt, "result": "failed"},
                    error_code=getattr(exc, "code", "AUTO_REPAIR_FAILED"),
                )
            db.commit()
        raise

    with session_factory() as db:
        task = db.get(Task, task_id)
        run = run_for_task(db, task_id)
        repair = db.get(RepairAttempt, repair_id)
        tool = db.get(ToolExecution, tool_id)
        source = db.get(CodeVersion, source_code_version_id)
        if not task or not run or not repair or not tool or not source:
            raise QualityGateError("REPAIR_CONTEXT_MISSING", {"attempt": attempt})
        manifest = {
            **dict(source.manifest_json),
            "development_run_id": run.id,
            "repair_attempt": attempt,
            "repair_source_code_version_id": source.id,
            "product_context": product_context,
            "generated_files": [item.path for item in materialized.files],
            "provider": provider.name,
            "model": provider.model,
            "provider_verification": provider.verification,
        }
        repaired = CodeVersion(
            project_id=task.project_id,
            version=version,
            commit_ref=materialized.commit_ref,
            test_status="testing",
            manifest_json=manifest,
        )
        db.add(repaired)
        db.flush()
        for item in materialized.files:
            db.add(
                CodeFile(
                    code_version_id=repaired.id,
                    path=item.path,
                    language=item.language,
                    product_purpose=item.product_purpose,
                    sha256=file_sha256(item.content),
                    size_bytes=len(item.content.encode("utf-8")),
                )
            )
        repair.status = "succeeded"
        repair.repaired_code_version_id = repaired.id
        repair.usage_json = dict(call.usage)
        repair.completed_at = datetime.now(UTC)
        project = db.get(Project, task.project_id)
        credential_id = task.checkpoint_json.get("credential_ref_id")
        credential = db.get(CredentialRef, credential_id) if credential_id else None
        if not project:
            raise QualityGateError("REPAIR_CONTEXT_MISSING", {"attempt": attempt})
        record_usage(
            db,
            settings=settings,
            owner_id=project.owner_id,
            project_id=project.id,
            task_id=task.id,
            credential=credential,
            operation="repair",
            provider=provider.name,
            model=provider.model,
            usage=call.usage,
            trace_id=task.trace_id,
        )
        finish_tool(
            tool,
            output_summary={
                "attempt": attempt,
                "code_version_id": repaired.id,
                "commit_ref": repaired.commit_ref,
            },
        )
        source.test_status = "quality_failed"
        run.code_version_id = repaired.id
        run.current_step = "automatic_repair"
        workspace = db.get(DevelopmentWorkspace, run.workspace_id)
        if workspace:
            workspace.current_commit_ref = repaired.commit_ref
            workspace.file_count = len(materialized.files)
            workspace.size_bytes = materialized.total_bytes
        task.checkpoint_json = {
            **task.checkpoint_json,
            "last_completed_step": "contract_validated",
            "code_version_id": repaired.id,
            "commit_ref": repaired.commit_ref,
            "repair_attempt": attempt,
        }
        _append_event(
            db,
            task,
            EventType.RETRY.value,
            f"第 {attempt} 次自动修复已生成新代码版本，正在重新测试。",
            {
                "attempt": attempt,
                "code_version_id": repaired.id,
                "commit_ref": repaired.commit_ref,
            },
        )
        db.commit()
        return repaired.id


def _rollback_last_good(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    task_id: str,
) -> str | None:
    with session_factory() as db:
        task = db.get(Task, task_id)
        run = run_for_task(db, task_id)
        if not task or not run:
            return None
        last_good = db.scalar(
            select(CodeVersion)
            .where(
                CodeVersion.project_id == task.project_id,
                CodeVersion.test_status == "quality_passed",
            )
            .order_by(CodeVersion.version.desc())
            .limit(1)
        )
        if not last_good:
            return None
        restore_commit(
            settings=settings,
            project_id=task.project_id,
            commit_ref=last_good.commit_ref,
        )
        workspace = db.get(DevelopmentWorkspace, run.workspace_id)
        if workspace:
            workspace.current_commit_ref = last_good.commit_ref
        task.checkpoint_json = {
            **task.checkpoint_json,
            "rolled_back_to_code_version_id": last_good.id,
            "rolled_back_to_commit_ref": last_good.commit_ref,
        }
        db.commit()
        return last_good.id


def execute_quality_and_preview(
    session_factory: sessionmaker[Session],
    settings: Settings,
    provider: AIProvider,
    preview_manager: GeneratedPreviewManager,
    *,
    task_id: str,
) -> tuple[str, str]:
    with session_factory() as db:
        task = db.get(Task, task_id)
        run = run_for_task(db, task_id)
        if not task or not run or not run.code_version_id:
            raise QualityGateError("QUALITY_CONTEXT_MISSING", {"task_id": task_id})
        provider_name = run.provider
        code_version_id = run.code_version_id
        existing_preview = db.scalar(
            select(Preview).where(
                Preview.project_id == task.project_id,
                Preview.code_version_id == code_version_id,
                Preview.status == "ready",
            )
        )
        if existing_preview:
            return code_version_id, existing_preview.id

    failures: list[dict[str, Any]] = []
    for repair_count in range(settings.quality_max_repairs + 1):
        attempt = repair_count + 1
        failures = _run_code_checks(
            session_factory,
            settings,
            task_id=task_id,
            code_version_id=code_version_id,
            attempt=attempt,
            provider_name=provider_name,
        )
        if not failures:
            runtime_failure, preview_id = _provision_and_smoke_preview(
                session_factory,
                settings,
                preview_manager,
                task_id=task_id,
                code_version_id=code_version_id,
                attempt=attempt,
                provider_name=provider_name,
            )
            if not runtime_failure:
                with session_factory() as db:
                    code_version = db.get(CodeVersion, code_version_id)
                    task = db.get(Task, task_id)
                    run = run_for_task(db, task_id)
                    if not code_version or not task or not run:
                        raise QualityGateError("QUALITY_CONTEXT_MISSING", {})
                    code_version.test_status = "quality_passed"
                    code_version.manifest_json = {
                        **dict(code_version.manifest_json),
                        "quality_gate": {
                            "status": "passed",
                            "attempt": attempt,
                            "checks": ["compile", "pytest", "runtime_smoke"],
                        },
                    }
                    run.current_step = "quality_passed"
                    task.checkpoint_json = {
                        **task.checkpoint_json,
                        "last_completed_step": "quality_passed",
                        "code_version_id": code_version.id,
                        "preview_id": preview_id,
                    }
                    db.commit()
                return code_version_id, preview_id
            failures = [runtime_failure]

        with session_factory() as db:
            failed_version = db.get(CodeVersion, code_version_id)
            if failed_version:
                failed_version.test_status = "quality_failed"
                failed_version.manifest_json = {
                    **dict(failed_version.manifest_json),
                    "quality_gate": {"status": "failed", "attempt": attempt, "checks": failures},
                }
                db.commit()
        if repair_count >= settings.quality_max_repairs:
            rolled_back = _rollback_last_good(session_factory, settings, task_id=task_id)
            raise QualityGateError(
                "QUALITY_GATE_FAILED",
                {
                    "attempts": attempt,
                    "failures": failures,
                    "rolled_back_to_code_version_id": rolled_back,
                },
            )
        code_version_id = _repair_code(
            session_factory,
            settings,
            provider,
            task_id=task_id,
            source_code_version_id=code_version_id,
            attempt=repair_count + 1,
            failures=failures,
        )
    raise QualityGateError("QUALITY_GATE_FAILED", {"failures": failures})


def _provision_and_smoke_preview(
    session_factory: sessionmaker[Session],
    settings: Settings,
    preview_manager: GeneratedPreviewManager,
    *,
    task_id: str,
    code_version_id: str,
    attempt: int,
    provider_name: str | None,
) -> tuple[dict[str, Any] | None, str]:
    with session_factory() as db:
        task = db.get(Task, task_id)
        run = run_for_task(db, task_id)
        code_version = db.get(CodeVersion, code_version_id)
        project = db.get(Project, task.project_id) if task else None
        if not task or not run or not code_version or not project:
            raise QualityGateError("PREVIEW_CONTEXT_MISSING", {})
        existing = db.scalar(
            select(Preview).where(
                Preview.project_id == project.id,
                Preview.code_version_id == code_version.id,
            )
        )
        if existing:
            runtime = db.scalar(
                select(PreviewRuntime).where(PreviewRuntime.preview_id == existing.id)
            )
            if runtime and runtime.status == "ready":
                return None, existing.id
            if runtime:
                preview_manager.stop(runtime.process_ref)
                db.delete(runtime)
                db.flush()
            preview = existing
            preview.status = "provisioning"
        else:
            config = PreviewConfig.model_validate(code_version.manifest_json["preview_config"])
            token = new_preview_token()
            preview = Preview(
                project_id=project.id,
                code_version_id=code_version.id,
                status="provisioning",
                preview_token=token,
                url_path=(
                    f"/api/v1/previews/{token}/page"
                    if config.template == "controlled_html_webapp_v1"
                    else f"/api/v1/previews/{token}/runtime"
                ),
                config_json=config.model_dump(mode="json"),
                expires_at=datetime.now(UTC) + timedelta(hours=settings.preview_ttl_hours),
            )
            db.add(preview)
            db.flush()
        runtime = PreviewRuntime(
            preview_id=preview.id,
            project_id=project.id,
            code_version_id=code_version.id,
            runtime_type="trusted_mock_subprocess",
            status="provisioning",
            process_ref=str(uuid4()),
        )
        db.add(runtime)
        tool = start_tool(
            db,
            run=run,
            tool_name="preview_runtime",
            side_effect="isolated_process",
            input_summary={"code_version_id": code_version.id},
        )
        preview_id = preview.id
        runtime_id = runtime.id
        process_ref = runtime.process_ref
        tool_id = tool.id
        db.commit()

    try:
        handle = preview_manager.start(
            process_ref=process_ref,
            project_id=_task_project_id(session_factory, task_id),
            provider=provider_name,
        )
        result, smoke_summary = preview_manager.smoke(handle)
    except QualityRuntimeError as exc:
        result = CommandResult(
            status="failed",
            exit_code=1,
            duration_ms=0,
            output_excerpt="生成应用预览启动失败。",
        )
        smoke_summary = {"error_code": exc.code}
        handle = None

    with session_factory() as db:
        task = db.get(Task, task_id)
        run = run_for_task(db, task_id)
        code_version = db.get(CodeVersion, code_version_id)
        preview = db.get(Preview, preview_id)
        runtime = db.get(PreviewRuntime, runtime_id)
        tool = db.get(ToolExecution, tool_id)
        if not task or not run or not code_version or not preview or not runtime or not tool:
            raise QualityGateError("PREVIEW_CONTEXT_MISSING", {})
        _persist_result(
            db,
            task=task,
            run=run,
            code_version=code_version,
            kind="runtime_smoke",
            attempt=attempt,
            result=result,
            summary=smoke_summary,
        )
        now = datetime.now(UTC)
        if result.status == "passed" and handle:
            preview.status = "ready"
            runtime.status = "ready"
            runtime.host = handle.host
            runtime.port = handle.port
            runtime.base_url = handle.base_url
            runtime.health_json = smoke_summary
            runtime.started_at = now
            runtime.last_health_at = now
            finish_tool(
                tool,
                output_summary={
                    "preview_id": preview.id,
                    "runtime_type": runtime.runtime_type,
                    "smoke_status": "passed",
                },
            )
        else:
            preview.status = "failed"
            runtime.status = "failed"
            runtime.error_code = str(smoke_summary.get("error_code") or "RUNTIME_SMOKE_FAILED")
            runtime.stopped_at = now
            finish_tool(
                tool,
                output_summary={"preview_id": preview.id, "smoke_status": "failed"},
                error_code=runtime.error_code,
            )
            preview_manager.stop(runtime.process_ref)
        _append_event(
            db,
            task,
            EventType.PROGRESS.value,
            "真实生成应用预览冒烟已通过。" if result.status == "passed" else "生成应用预览未通过，准备有限修复。",
            {
                "checkpoint": "runtime_smoke",
                "status": result.status,
                "preview_id": preview.id,
                "code_version_id": code_version.id,
            },
        )
        db.commit()
    if result.status != "passed":
        return (
            {
                "kind": "runtime_smoke",
                "status": result.status,
                "output": result.output_excerpt,
                **smoke_summary,
            },
            preview_id,
        )
    return None, preview_id
