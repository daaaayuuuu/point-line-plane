from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import Artifact, AuditEvent, Confirmation, Preview, Project, RequirementSession
from app.models.enums import ArtifactStatus, ArtifactType, ProjectStage, ProjectStatus
from app.schemas.contracts import ChangeRequestContent, PrdContent, SolutionContent
from app.services.providers import (
    AIProvider,
    architect_solution_with_retry,
    write_prd_with_retry,
)

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    ProjectStage.REQUIREMENTS.value: {ProjectStage.PRD_REVIEW.value},
    ProjectStage.PRD_REVIEW.value: {ProjectStage.SOLUTION_REVIEW.value},
    ProjectStage.SOLUTION_REVIEW.value: {ProjectStage.DEVELOPMENT.value},
    ProjectStage.DEVELOPMENT.value: {ProjectStage.PREVIEW_REVIEW.value, ProjectStage.PAUSED.value},
    ProjectStage.PREVIEW_REVIEW.value: {
        ProjectStage.DEVELOPMENT.value,
        ProjectStage.SOLUTION_REVIEW.value,
        ProjectStage.DEPLOYMENT.value,
    },
    ProjectStage.DEPLOYMENT.value: {ProjectStage.DELIVERY.value},
    ProjectStage.PAUSED.value: {ProjectStage.DEVELOPMENT.value},
}


def transition(project: Project, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(project.stage, set()):
        raise ApiError(
            "INVALID_STAGE_TRANSITION",
            f"当前阶段 {project.stage} 不能进入 {target}。",
            409,
        )
    project.stage = target
    project.status = (
        ProjectStatus.PAUSED.value
        if target == ProjectStage.PAUSED.value
        else ProjectStatus.ACTIVE.value
    )


def record_audit(
    db: Session,
    *,
    project_id: str | None,
    actor_id: str | None,
    action: str,
    target_type: str,
    target_id: str | None,
    result: str,
    trace_id: str,
) -> None:
    db.add(
        AuditEvent(
            project_id=project_id,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            result=result,
            trace_id=trace_id,
        )
    )


def next_artifact_version(db: Session, project_id: str, artifact_type: str) -> int:
    current = db.scalar(
        select(func.max(Artifact.version)).where(
            Artifact.project_id == project_id,
            Artifact.type == artifact_type,
        )
    )
    return int(current or 0) + 1


def latest_artifact(db: Session, project_id: str, artifact_type: str) -> Artifact | None:
    return db.scalar(
        select(Artifact)
        .where(Artifact.project_id == project_id, Artifact.type == artifact_type)
        .order_by(Artifact.version.desc())
        .limit(1)
    )


def create_project(db: Session, *, owner_id: str, name: str, idea: str) -> Project:
    project = Project(owner_id=owner_id, name=name, idea=idea)
    db.add(project)
    db.flush()
    db.add(
        RequirementSession(
            project_id=project.id,
            answers_json={"messages": [{"role": "user", "content": idea, "kind": "idea"}]},
            missing_items_json=["target_user"],
            round=0,
            version=1,
        )
    )
    return project


def _summary(text: str, limit: int = 220) -> str:
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 1] + "…"


def build_prd(
    project: Project, requirement_text: str, revision_note: str | None = None
) -> PrdContent:
    content = PrdContent(
        title=f"{project.name}｜M1 产品需求文档",
        summary=f"围绕“{_summary(project.idea, 120)}”构建一个受控文本型 AI Web Agent。",
        target_users=["有明确业务目标、但无法独立完成 AI 产品开发的非技术用户"],
        problem=f"用户需要把输入内容转化为可直接使用的结构化结果。补充说明：{_summary(requirement_text)}",
        core_flow=["用户输入文本", "系统校验并调用配置模型", "展示结构化结果", "保存本次运行历史"],
        features=[
            "单一文本输入",
            "结构化结果展示",
            "运行状态与产品语言错误",
            "同一预览内的历史记录",
        ],
        scope={
            "included": ["文本输入", "配置模型调用", "结构化输出", "历史记录", "响应式 Web 预览"],
            "excluded": ["文件与 RAG", "音视频生成", "目标产品账户系统", "支付", "任意代码执行"],
        },
        acceptance_criteria=[
            "用户可以提交非空文本并获得包含摘要、要点和下一步的结果",
            "刷新项目工作区后 PRD、方案、任务和确认记录仍然存在",
            "模型失败时显示可理解错误，不显示密钥或程序堆栈",
        ],
        assumptions=[
            "首版只支持文本型 AI Web Agent",
            "模型供应商与真实费用由环境配置并在真实验收前确认",
        ],
        source_notes=[_summary(project.idea, 500), _summary(requirement_text, 1_000)],
        revision_notes=[revision_note] if revision_note else [],
    )
    return PrdContent.model_validate(content.model_dump())


def create_prd_artifact(
    db: Session,
    project: Project,
    requirement_text: str,
    *,
    provider: AIProvider | None = None,
    max_attempts: int = 2,
) -> Artifact:
    existing = latest_artifact(db, project.id, ArtifactType.PRD.value)
    if existing:
        existing.status = ArtifactStatus.SUPERSEDED.value
    version = next_artifact_version(db, project.id, ArtifactType.PRD.value)
    content = (
        write_prd_with_retry(
            provider,
            project_name=project.name,
            idea=project.idea,
            requirement_text=requirement_text,
            max_attempts=max_attempts,
        )
        if provider
        else build_prd(project, requirement_text)
    )
    artifact = Artifact(
        project_id=project.id,
        type=ArtifactType.PRD.value,
        version=version,
        status=ArtifactStatus.DRAFT.value,
        content_json=content.model_dump(mode="json"),
    )
    db.add(artifact)
    project.current_artifact_version = max(project.current_artifact_version, version)
    return artifact


def create_prd_artifact_from_content(
    db: Session,
    project: Project,
    content: PrdContent,
) -> Artifact:
    existing = latest_artifact(db, project.id, ArtifactType.PRD.value)
    if existing:
        existing.status = ArtifactStatus.SUPERSEDED.value
    version = next_artifact_version(db, project.id, ArtifactType.PRD.value)
    artifact = Artifact(
        project_id=project.id,
        type=ArtifactType.PRD.value,
        version=version,
        status=ArtifactStatus.DRAFT.value,
        content_json=content.model_dump(mode="json"),
    )
    db.add(artifact)
    project.current_artifact_version = max(project.current_artifact_version, version)
    return artifact


def ingest_requirement(
    db: Session,
    project: Project,
    text: str,
    kind: str = "message",
    *,
    question_id: str | None = None,
    provider: AIProvider | None = None,
    max_attempts: int = 2,
) -> Artifact | None:
    if project.stage == ProjectStage.REQUIREMENTS.value:
        requirement = project.requirement_session
        if requirement is None:
            raise ApiError("REQUIREMENT_SESSION_MISSING", "需求会话无法恢复，请联系管理员。", 500)
        answers = deepcopy(requirement.answers_json)
        missing = list(requirement.missing_items_json)
        expected_question_id = missing[0] if missing else None
        if kind != "upload" and question_id != expected_question_id:
            raise ApiError(
                "STALE_REQUIREMENT_QUESTION",
                "需求问题已更新，请刷新后回答当前问题。",
                409,
            )
        answered_question_id = "uploaded_prd" if kind == "upload" else expected_question_id
        answers.setdefault("messages", []).append(
            {
                "role": "user",
                "content": text,
                "kind": kind,
                "question_id": answered_question_id,
            }
        )
        requirement.answers_json = answers
        # One focused answer is enough for the first PRD. The original idea plus this
        # answer provide the provider with the user, problem, and desired direction;
        # later refinements belong in PRD review instead of extra chat rounds.
        requirement.missing_items_json = []
        requirement.round += 1
        if requirement.missing_items_json:
            return None
        collected = "\n".join(
            str(item.get("content", ""))
            for item in answers.get("messages", [])
            if item.get("kind") != "idea"
        )
        artifact = create_prd_artifact(
            db,
            project,
            collected or text,
            provider=provider,
            max_attempts=max_attempts,
        )
        transition(project, ProjectStage.PRD_REVIEW.value)
        return artifact

    if project.stage == ProjectStage.PRD_REVIEW.value:
        if question_id is not None:
            raise ApiError(
                "STALE_REQUIREMENT_QUESTION",
                "该需求问题已经回答，请刷新后再修改 PRD。",
                409,
            )
        current = latest_artifact(db, project.id, ArtifactType.PRD.value)
        if not current:
            raise ApiError("PRD_MISSING", "当前 PRD 不存在，无法修改。", 409)
        return revise_artifact(db, project, current, text)

    raise ApiError("INVALID_PROJECT_STAGE", "当前阶段不能继续补充需求。", 409)


def build_solution(project: Project, prd: Artifact) -> SolutionContent:
    prd_content = PrdContent.model_validate(prd.content_json)
    return SolutionContent.model_validate(
        {
            "title": f"{project.name}｜推荐产品与技术方案",
            "summary": "采用一个受控文本 Agent 模板完成首条纵向切片，先验证核心价值与结果质量。",
            "recommended_approach": "模块化单体：Next.js 正式前端、FastAPI API、关系型业务状态和持久化任务；模型通过后端 provider 边界调用。",
            "product_scope": prd_content.scope["included"],
            "deferred": prd_content.scope["excluded"],
            "user_costs": [
                {
                    "item": "本地 M1",
                    "estimate": "无新增云资源费用",
                    "note": "使用 SQLite 与本地受控预览",
                },
                {
                    "item": "真实模型",
                    "estimate": "按所选供应商实际用量",
                    "note": "启用前需要配置自己的 Key 并确认费用",
                },
            ],
            "external_accounts": ["M1 mock 验收不需要外部账号；真实模型验收需要对应供应商账号"],
            "risks": [
                "当前不是任意代码沙箱",
                "本地预览不等于公网托管",
                "模型输出质量仍需真实 Key 冒烟验证",
            ],
            "deliverables": [
                "版本化 PRD",
                "推荐方案",
                "持久化开发任务",
                "绑定代码版本的可操作文本 Agent 预览",
            ],
            "architecture": {
                "application": "modular_monolith",
                "backend": "FastAPI + SQLAlchemy",
                "frontend": "Next.js",
                "database": "SQLite for local M1",
                "task_runtime": "persistent table + controlled single-process executor",
                "preview_template": "controlled_text_agent_v1",
            },
        }
    )


def create_solution_artifact(
    db: Session,
    project: Project,
    prd: Artifact,
    *,
    provider: AIProvider | None = None,
    max_attempts: int = 2,
) -> Artifact:
    version = next_artifact_version(db, project.id, ArtifactType.SOLUTION.value)
    prd_content = PrdContent.model_validate(prd.content_json)
    content = (
        architect_solution_with_retry(
            provider,
            project_name=project.name,
            prd=prd_content,
            max_attempts=max_attempts,
        )
        if provider
        else build_solution(project, prd)
    )
    artifact = Artifact(
        project_id=project.id,
        type=ArtifactType.SOLUTION.value,
        version=version,
        status=ArtifactStatus.DRAFT.value,
        content_json=content.model_dump(mode="json"),
    )
    db.add(artifact)
    project.current_artifact_version = max(project.current_artifact_version, version)
    return artifact


def revise_artifact(db: Session, project: Project, artifact: Artifact, comment: str) -> Artifact:
    artifact.status = ArtifactStatus.SUPERSEDED.value
    content = deepcopy(artifact.content_json)
    notes = list(content.get("revision_notes", []))
    notes.append(comment)
    content["revision_notes"] = notes
    content["summary"] = (
        f"{content.get('summary', '')} 已根据第 {artifact.version + 1} 版意见更新。"
    )

    if artifact.type == ArtifactType.PRD.value:
        validated: dict[str, Any] = PrdContent.model_validate(content).model_dump(mode="json")
    else:
        validated = SolutionContent.model_validate(content).model_dump(mode="json")
    revised = Artifact(
        project_id=project.id,
        type=artifact.type,
        version=next_artifact_version(db, project.id, artifact.type),
        status=ArtifactStatus.DRAFT.value,
        content_json=validated,
    )
    db.add(revised)
    project.current_artifact_version = max(project.current_artifact_version, revised.version)
    return revised


def confirm_artifact(
    db: Session,
    *,
    project: Project,
    artifact: Artifact,
    artifact_type: str,
    decision: str,
    comment: str | None,
    provider: AIProvider | None = None,
    max_attempts: int = 2,
) -> tuple[Confirmation | None, Artifact | None]:
    if artifact.project_id != project.id or artifact.type != artifact_type:
        raise ApiError("ARTIFACT_MISMATCH", "该产物不属于当前项目或类型不匹配。", 400)
    current = latest_artifact(db, project.id, artifact_type)
    if current is None or current.id != artifact.id:
        raise ApiError("STALE_ARTIFACT", "这不是当前最新版本，请刷新后再操作。", 409)

    expected_stage = (
        ProjectStage.PRD_REVIEW.value
        if artifact_type == ArtifactType.PRD.value
        else ProjectStage.SOLUTION_REVIEW.value
    )
    existing = db.scalar(
        select(Confirmation).where(
            Confirmation.artifact_id == artifact.id,
            Confirmation.decision == decision,
        )
    )
    if existing:
        next_item = (
            latest_artifact(db, project.id, ArtifactType.SOLUTION.value)
            if artifact_type == ArtifactType.PRD.value and decision == "confirm"
            else None
        )
        return existing, next_item

    if project.stage != expected_stage:
        raise ApiError("INVALID_PROJECT_STAGE", "当前阶段不能确认这个产物。", 409)

    if decision == "revise":
        if not comment:
            raise ApiError("REVISION_COMMENT_REQUIRED", "提出修改时必须填写修改意见。", 422)
        confirmation = Confirmation(
            project_id=project.id,
            type=artifact_type,
            artifact_id=artifact.id,
            decision="revise",
            comment=comment,
        )
        db.add(confirmation)
        return confirmation, revise_artifact(db, project, artifact, comment)

    confirmation = Confirmation(
        project_id=project.id,
        type=artifact_type,
        artifact_id=artifact.id,
        decision="confirm",
        comment=comment,
    )
    db.add(confirmation)
    artifact.status = ArtifactStatus.CONFIRMED.value
    if artifact_type == ArtifactType.PRD.value:
        transition(project, ProjectStage.SOLUTION_REVIEW.value)
        next_item = create_solution_artifact(
            db,
            project,
            artifact,
            provider=provider,
            max_attempts=max_attempts,
        )
    else:
        transition(project, ProjectStage.DEVELOPMENT.value)
        project.development_revision += 1
        next_item = None
    return confirmation, next_item


NEW_SCOPE_TERMS = {
    "新增",
    "增加模块",
    "登录",
    "注册",
    "支付",
    "会员",
    "上传",
    "文件",
    "知识库",
    "rag",
    "语音",
    "音频",
    "视频",
    "图片生成",
    "第三方系统",
    "企业微信",
}


def classify_feedback(text: str) -> tuple[str, str]:
    normalized = text.lower()
    hits = [term for term in NEW_SCOPE_TERMS if term in normalized]
    if hits:
        return (
            "new_scope",
            f"反馈包含首版范围外能力：{'、'.join(sorted(hits))}，需要重新确认方案影响。",
        )
    return "in_scope", "反馈集中在现有文本输入、结构化输出或页面体验内，可进入当前范围修改。"


def apply_feedback(
    db: Session, project: Project, feedback: str
) -> tuple[str, str, Artifact | None, Artifact | None]:
    if project.stage != ProjectStage.PREVIEW_REVIEW.value:
        raise ApiError("INVALID_PROJECT_STAGE", "只有待预览验收阶段可以提交这类反馈。", 409)
    classification, reason = classify_feedback(feedback)
    if classification == "in_scope":
        preview = db.scalar(
            select(Preview)
            .where(Preview.project_id == project.id)
            .order_by(Preview.created_at.desc())
            .limit(1)
        )
        change_request = Artifact(
            project_id=project.id,
            type=ArtifactType.CHANGE_REQUEST.value,
            version=next_artifact_version(db, project.id, ArtifactType.CHANGE_REQUEST.value),
            status=ArtifactStatus.CONFIRMED.value,
            content_json=ChangeRequestContent(
                title="预览范围内修改请求",
                feedback=feedback,
                classification="in_scope",
                reason=reason,
                source_preview_id=preview.id if preview else None,
                source_code_version_id=preview.code_version_id if preview else None,
            ).model_dump(mode="json"),
        )
        db.add(change_request)
        project.current_artifact_version = max(
            project.current_artifact_version, change_request.version
        )
        transition(project, ProjectStage.DEVELOPMENT.value)
        project.development_revision += 1
        return classification, reason, None, change_request

    transition(project, ProjectStage.SOLUTION_REVIEW.value)
    current = latest_artifact(db, project.id, ArtifactType.SOLUTION.value)
    if current is None:
        raise ApiError("SOLUTION_MISSING", "方案产物不存在，无法处理新增范围。", 409)
    revised = revise_artifact(db, project, current, f"预览反馈（新增范围）：{feedback}")
    return classification, reason, revised, None
