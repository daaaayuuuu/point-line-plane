from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Artifact,
    CodeVersion,
    Confirmation,
    Preview,
    PreviewAcceptance,
    Project,
    Task,
)
from app.models.enums import ProjectStage
from app.schemas.contracts import (
    ArtifactResponse,
    CodeVersionResponse,
    ConfirmationResponse,
    NextAction,
    PreviewRunResponse,
    PreviewSummary,
    ProjectDetail,
    ProjectSummary,
    PrdContent,
    Question,
    TaskResponse,
)

REQUIREMENT_QUESTIONS = [
    Question(
        id="target_user",
        label="最希望谁来使用这个产品？他们现在最痛的点是什么？",
        reason="这决定首版为谁解决问题，避免功能泛化。",
    ),
    Question(
        id="core_output",
        label="用户提交一段文本后，最希望拿到什么结果？",
        reason="这决定核心结果的结构和页面反馈。",
    ),
    Question(
        id="success_criteria",
        label="怎样算首版已经可用？请给一个最关键的验收标准。",
        reason="这让后续开发和预览有明确的完成线。",
    ),
]


def artifact_response(artifact: Artifact) -> ArtifactResponse:
    content = (
        PrdContent.model_validate(artifact.content_json).model_dump(mode="json")
        if artifact.type == "prd"
        else artifact.content_json
    )
    return ArtifactResponse(
        id=artifact.id,
        project_id=artifact.project_id,
        type=artifact.type,
        version=artifact.version,
        status=artifact.status,
        content=content,
        created_at=artifact.created_at,
    )


def confirmation_response(confirmation: Confirmation) -> ConfirmationResponse:
    return ConfirmationResponse.model_validate(confirmation)


def task_response(task: Task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        project_id=task.project_id,
        stage=task.stage,
        status=task.status,
        progress=task.progress,
        attempts=task.attempts,
        max_attempts=task.max_attempts,
        checkpoint=task.checkpoint_json,
        trace_id=task.trace_id,
        error_code=task.error_code,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def code_version_response(code_version: CodeVersion) -> CodeVersionResponse:
    return CodeVersionResponse(
        id=code_version.id,
        project_id=code_version.project_id,
        version=code_version.version,
        commit_ref=code_version.commit_ref,
        test_status=code_version.test_status,
        manifest=code_version.manifest_json,
        created_at=code_version.created_at,
    )


def preview_run_response(run: object) -> PreviewRunResponse:
    return PreviewRunResponse(
        id=run.id,
        input=run.input_text,
        result=run.output_json,
        provider=run.provider,
        model=run.model,
        provider_verification=run.usage_json.get("provider_verification", "unverified"),
        usage=run.usage_json,
        latency_ms=run.latency_ms,
        created_at=run.created_at,
    )


def _latest_task(db: Session, project_id: str) -> Task | None:
    return db.scalar(
        select(Task)
        .where(Task.project_id == project_id)
        .order_by(Task.created_at.desc(), Task.id.desc())
        .limit(1)
    )


def _latest_preview(db: Session, project_id: str) -> Preview | None:
    return db.scalar(
        select(Preview)
        .where(Preview.project_id == project_id)
        .order_by(Preview.created_at.desc(), Preview.id.desc())
        .limit(1)
    )


def preview_status(preview: Preview) -> str:
    expires_at = preview.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return "expired"
    return preview.status


def preview_is_ready(preview: Preview | None) -> bool:
    return bool(preview and preview_status(preview) == "ready")


def project_summary(db: Session, project: Project) -> ProjectSummary:
    task = _latest_task(db, project.id)
    preview = _latest_preview(db, project.id)
    return ProjectSummary(
        id=project.id,
        name=project.name,
        idea=project.idea,
        stage=project.stage,
        status=project.status,
        scope=project.scope,
        current_artifact_version=project.current_artifact_version,
        task_status=task.status if task else None,
        task_progress=task.progress if task else None,
        preview_token=preview.preview_token if preview_is_ready(preview) else None,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def next_action(project: Project, task: Task | None, preview: Preview | None) -> NextAction:
    if project.stage == ProjectStage.REQUIREMENTS.value:
        missing = (
            project.requirement_session.missing_items_json
            if project.requirement_session is not None
            else []
        )
        question_by_id = {question.id: question for question in REQUIREMENT_QUESTIONS}
        current_question = question_by_id.get(missing[0]) if missing else None
        return NextAction(
            code="answer_requirements",
            message="请回答这一个产品问题，提交后会直接生成第一版 PRD。",
            questions=[current_question] if current_question else [],
        )
    if project.stage == ProjectStage.PRD_REVIEW.value:
        return NextAction(code="review_prd", message="请确认当前 PRD，或提出具体修改意见。")
    if project.stage == ProjectStage.SOLUTION_REVIEW.value:
        return NextAction(
            code="review_solution",
            message="请确认推荐方案中的功能范围、费用、账号和风险。",
        )
    if project.stage == ProjectStage.DEVELOPMENT.value:
        if task and task.status in {"queued", "running"}:
            return NextAction(code="watch_task", message="开发任务正在执行，可查看实时进度。")
        return NextAction(code="start_development", message="方案已确认，可以启动开发任务。")
    if project.stage == ProjectStage.PREVIEW_REVIEW.value:
        if preview_is_ready(preview):
            return NextAction(
                code="review_preview", message="预览已就绪，请操作核心流程并提交反馈。"
            )
        if preview:
            return NextAction(
                code="preview_expired",
                message="当前预览已过期，不能继续验收或提交反馈。",
            )
        return NextAction(code="preview_unavailable", message="当前没有可验收的预览。")
    if project.stage == ProjectStage.DEPLOYMENT.value:
        return NextAction(
            code="watch_deployment",
            message="部署任务已获得授权，请查看部署状态、HTTPS 验证或失败回退信息。",
        )
    if project.stage == ProjectStage.DELIVERY.value:
        return NextAction(code="review_delivery", message="正式部署已完成，可以准备交付包。")
    return NextAction(
        code="recover_task",
        message="任务已暂停。请查看错误摘要和最后检查点后再恢复。",
    )


def project_detail(db: Session, project: Project) -> ProjectDetail:
    artifacts = list(
        db.scalars(
            select(Artifact)
            .where(Artifact.project_id == project.id)
            .order_by(Artifact.type, Artifact.version.desc())
        )
    )
    latest_by_type: dict[str, Artifact] = {}
    for item in artifacts:
        latest_by_type.setdefault(item.type, item)

    confirmations = list(
        db.scalars(
            select(Confirmation)
            .where(Confirmation.project_id == project.id)
            .order_by(Confirmation.created_at)
        )
    )
    task = _latest_task(db, project.id)
    preview = _latest_preview(db, project.id)
    preview_accepted = db.scalar(
        select(PreviewAcceptance.id)
        .where(PreviewAcceptance.project_id == project.id)
        .limit(1)
    ) is not None
    summary = project_summary(db, project)
    preview_summary: PreviewSummary | None = None
    if preview_is_ready(preview):
        code_version = db.get(CodeVersion, preview.code_version_id)
        if code_version:
            preview_summary = PreviewSummary(
                id=preview.id,
                token=preview.preview_token,
                status=preview_status(preview),
                url_path=preview.url_path,
                code_version=code_version.version,
                expires_at=preview.expires_at,
            )

    return ProjectDetail(
        **summary.model_dump(),
        latest_artifacts=[artifact_response(item) for item in latest_by_type.values()],
        confirmations=[confirmation_response(item) for item in confirmations],
        active_task=task_response(task) if task else None,
        preview=preview_summary,
        preview_accepted=preview_accepted,
        next_action=next_action(project, task, preview),
    )
