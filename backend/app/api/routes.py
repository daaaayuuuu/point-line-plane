from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, Db, owned_project
from app.core.config import Settings
from app.core.errors import ApiError, not_found
from app.core.security import (
    new_session_token,
    secret_hash,
    session_token_hash,
    verify_invite_code,
)
from app.models import (
    Artifact,
    BackupRecord,
    BetaInvite,
    CodeFile,
    CodeVersion,
    Confirmation,
    CostAuthorization,
    CredentialRef,
    DeliveryPackage,
    Deployment,
    DeploymentAuthorization,
    DevelopmentRun,
    GithubSync,
    Preview,
    PreviewAcceptance,
    PreviewRun,
    PreviewRuntime,
    ProductGraph,
    Project,
    QualityRun,
    QuotaAccount,
    RepairAttempt,
    Session,
    Task,
    TaskEvent,
    UsageLedger,
    User,
)
from app.models.enums import ArtifactType, EventType, ProjectStage, ProjectStatus
from app.schemas.contracts import (
    AgentResult,
    ArtifactListResponse,
    ArtifactResponse,
    AuthResponse,
    BackupCreateRequest,
    BackupResponse,
    BetaInviteCreateRequest,
    BetaInviteResponse,
    CloudCredentialCreateRequest,
    CloudCredentialListResponse,
    CloudCredentialResponse,
    CodeFileContentResponse,
    CodexAccountResponse,
    CodexConversationListResponse,
    CodexConversationMessage,
    CodexConversationResponse,
    CodexConversationSummary,
    CodexLoginResponse,
    CodexReasoningProgressResponse,
    CodexRequirementResponse,
    ConfirmationActionResponse,
    ConfirmationRequest,
    ConfirmProductDecisionRequest,
    CostAuthorizationResponse,
    CostQuoteRequest,
    CredentialRevokeRequest,
    CredentialVerifyRequest,
    DecisionCenterResponse,
    DeliveryPackageCreateRequest,
    DeliveryPackageListResponse,
    DeliveryPackageResponse,
    DeploymentAuthorizationListResponse,
    DeploymentAuthorizationRequest,
    DeploymentAuthorizationResponse,
    DeploymentListResponse,
    DeploymentResponse,
    DeploymentRollbackRequest,
    DeploymentStartRequest,
    DevelopmentRunListResponse,
    DevelopmentRunResponse,
    DevelopmentStartRequest,
    DevelopmentWorkspaceResponse,
    FeedbackResponse,
    FindingResolutionResponse,
    GithubSyncRequest,
    GithubSyncResponse,
    InviteLoginRequest,
    ModelCredentialCreateRequest,
    ModelCredentialListResponse,
    ModelCredentialResponse,
    OkResponse,
    OperationsMetricsResponse,
    PlatformCapabilitiesResponse,
    PrdContent,
    PreviewAcceptanceRequest,
    PreviewAcceptanceResponse,
    PreviewConfig,
    PreviewFeedbackRequest,
    PreviewResponse,
    PreviewRunRequest,
    PreviewRunResponse,
    PreviewRuntimeResponse,
    ProductDashboardResponse,
    ProductDecisionActionResponse,
    ProductGraphResponse,
    ProjectCreateRequest,
    ProjectDetail,
    ProjectListResponse,
    QualityHistoryResponse,
    QuotaResponse,
    RequirementMessageRequest,
    RequirementResponse,
    ResolveFindingRequest,
    RuntimeAnalyzeResponse,
    RuntimeHistoryResponse,
    SimulationRunResponse,
    SimulationStartRequest,
    TaskResponse,
    UsageLedgerListResponse,
    UsageLedgerResponse,
    UsageSummaryResponse,
)
from app.services.codex_auth import CodexAccount, CodexAuthError, CodexLoginAttempt
from app.services.codex_requirements import run_codex_requirement_turn
from app.services.credentials import (
    SecretVault,
    consume_authorization,
    create_cost_authorization,
    ensure_quota_account,
    masked_hint,
    owned_cost_authorization,
    owned_credential,
    provider_for_credential,
    record_usage,
    remaining_quota,
)
from app.services.delivery import (
    create_delivery_package,
    delivery_response,
    github_sync_response,
    owned_delivery,
    package_path,
    sync_delivery_to_github,
)
from app.services.deployment import (
    acceptance_response,
    authorization_response,
    create_deployment_authorization,
    deployment_response,
    owned_deployment,
    owned_deployment_authorization,
    start_deployment_record,
)
from app.services.development import (
    code_file_metadata,
    development_run_response,
    owned_development_run,
    owned_workspace,
    preview_runtime_response,
    quality_run_response,
    repair_attempt_response,
    workspace_response,
)
from app.services.development_runtime import ControlledCodingError, read_file_at_commit
from app.services.file_ingestion import extract_upload_text
from app.services.operations import (
    backup_response,
    beta_invite_response,
    create_backup,
    enforce_rate_limit,
    operations_metrics,
    require_operations_token,
)
from app.services.presenters import (
    artifact_response,
    code_version_response,
    confirmation_response,
    preview_run_response,
    project_detail,
    project_summary,
    task_response,
)
from app.services.product_experience import (
    active_graph,
    advance_simulation,
    change_request_response,
    confirm_product_decision,
    dashboard_next_action,
    dashboard_response,
    decision_center_response,
    decision_response,
    finding_response,
    graph_response,
    initialize_product_graph,
    owned_decision,
    owned_finding,
    owned_simulation,
    require_active_graph,
    resolve_finding,
    simulation_response,
    start_simulation,
)
from app.services.providers import generate_with_retry
from app.services.quality_runtime import QualityRuntimeError
from app.services.task_runner import retry_failed_task, start_development_task
from app.services.workflow import (
    apply_feedback,
    confirm_artifact,
    create_prd_artifact_from_content,
    create_project,
    ingest_requirement,
    latest_artifact,
    record_audit,
    transition,
)

router = APIRouter(prefix="/api/v1")


def trace_id(request: Request) -> str:
    return request.state.trace_id


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/capabilities", response_model=PlatformCapabilitiesResponse)
def platform_capabilities(request: Request, _user: CurrentUser) -> PlatformCapabilitiesResponse:
    settings: Settings = request.app.state.settings
    ai_mode = (
        "mock"
        if settings.ai_provider == "mock"
        else "verified"
        if settings.ai_provider_verified
        else "unverified"
    )
    return PlatformCapabilitiesResponse(
        ai_provider_mode=ai_mode,
        ai_provider=settings.ai_provider,
        ai_model=settings.ai_model,
        generated_execution_mode=settings.generated_execution_mode,
        deployment_enabled=settings.deployment_enabled,
        deployment_mode=settings.deployment_mode,
        deployment_provider="volcano_engine",
        deployment_region=settings.deployment_default_region,
        github_sync_mode=settings.github_sync_mode,
    )


@router.get("/health/ready")
def readiness(db: Db) -> dict[str, str]:
    try:
        database_ok = db.scalar(select(text("1"))) == 1
        migration = db.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception as exc:
        raise ApiError("DATABASE_NOT_READY", "数据库尚未准备好。", 503) from exc
    if not database_ok or migration != "20260821_0008":
        raise ApiError("MIGRATION_NOT_READY", "数据库迁移尚未完成。", 503)
    return {"status": "ready", "migration": migration}


@router.post(
    "/operations/beta-invites",
    response_model=BetaInviteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_beta_invite(
    body: BetaInviteCreateRequest,
    request: Request,
    db: Db,
) -> BetaInviteResponse:
    require_operations_token(request)
    expiry = body.expires_at
    if expiry and (expiry if expiry.tzinfo else expiry.replace(tzinfo=UTC)) <= datetime.now(UTC):
        raise ApiError("INVITE_EXPIRY_INVALID", "邀请码有效期必须晚于当前时间。", 422)
    code_hash = secret_hash(body.code.get_secret_value().strip())
    if db.scalar(select(BetaInvite).where(BetaInvite.code_hash == code_hash)):
        raise ApiError("INVITE_ALREADY_EXISTS", "这个邀请码已存在。", 409)
    item = BetaInvite(
        code_hash=code_hash,
        label=body.label.strip(),
        max_uses=body.max_uses,
        expires_at=body.expires_at,
    )
    db.add(item)
    db.commit()
    return beta_invite_response(item)


@router.get("/operations/beta-invites", response_model=list[BetaInviteResponse])
def list_beta_invites(request: Request, db: Db) -> list[BetaInviteResponse]:
    require_operations_token(request)
    items = list(db.scalars(select(BetaInvite).order_by(BetaInvite.created_at.desc()).limit(200)))
    return [beta_invite_response(item) for item in items]


@router.post(
    "/operations/backups",
    response_model=BackupResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_operations_backup(
    body: BackupCreateRequest,
    request: Request,
    db: Db,
) -> BackupResponse:
    require_operations_token(request)
    if not body.confirm:
        raise ApiError("BACKUP_CONFIRMATION_REQUIRED", "创建备份前需要明确确认。", 409)
    item = create_backup(db, request.app.state.settings)
    db.commit()
    return backup_response(item)


@router.get("/operations/backups", response_model=list[BackupResponse])
def list_operations_backups(request: Request, db: Db) -> list[BackupResponse]:
    require_operations_token(request)
    items = list(
        db.scalars(select(BackupRecord).order_by(BackupRecord.created_at.desc()).limit(100))
    )
    return [backup_response(item) for item in items]


@router.get("/operations/metrics", response_model=OperationsMetricsResponse)
def get_operations_metrics(request: Request, db: Db) -> OperationsMetricsResponse:
    require_operations_token(request)
    return operations_metrics(db, request.app.state.settings.database_url)


def _set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.app_env.lower() in {"production", "prod"},
        samesite="lax",
        path="/",
    )


def _complete_codex_login(
    *,
    account: CodexAccount,
    request: Request,
    response: Response,
    db: Db,
) -> User:
    settings: Settings = request.app.state.settings
    identity_hash = secret_hash(f"codex:{account.email}")
    user = db.scalar(select(User).where(User.invite_code_hash == identity_hash))
    stored_name = (user.quota or {}).get("codex_display_name") if user else None
    if not isinstance(stored_name, str) or not stored_name.strip():
        stored_name = None
    display_name = (account.display_name or stored_name or account.email)[:80]
    codex_display_name = account.display_name or stored_name
    if not user:
        user = User(
            display_name=display_name,
            invite_code_hash=identity_hash,
            quota={
                "projects": 10,
                "auth_provider": "codex",
                "codex_plan_type": account.plan_type,
                "codex_display_name": codex_display_name,
            },
        )
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            user = db.scalar(select(User).where(User.invite_code_hash == identity_hash))
            if not user:
                raise ApiError("CODEX_ACCOUNT_CONFLICT", "Codex 账号绑定失败，请重试。", 409)
    else:
        user.display_name = display_name
        user.quota = {
            **(user.quota or {}),
            "projects": int((user.quota or {}).get("projects", 10)),
            "auth_provider": "codex",
            "codex_plan_type": account.plan_type,
            "codex_display_name": codex_display_name,
        }

    opaque_token = new_session_token()
    login_session = Session(
        token_hash=session_token_hash(opaque_token, settings.session_secret.get_secret_value()),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(login_session)
    db.flush()
    record_audit(
        db,
        project_id=None,
        actor_id=user.id,
        action="codex_login",
        target_type="session",
        target_id=login_session.id,
        result="success",
        trace_id=trace_id(request),
    )
    db.commit()
    _set_session_cookie(response, settings, opaque_token)
    return user


def _codex_login_response(attempt: CodexLoginAttempt) -> CodexLoginResponse:
    account = (
        CodexAccountResponse(
            email=attempt.account.email,
            plan_type=attempt.account.plan_type,
            display_name=attempt.account.display_name,
        )
        if attempt.account
        else None
    )
    return CodexLoginResponse(
        attempt_id=attempt.attempt_id,
        status=attempt.status,
        auth_url=attempt.auth_url,
        account=account,
        error=attempt.error,
    )


@router.post("/auth/codex/start", response_model=CodexLoginResponse)
def start_codex_login(
    request: Request,
    response: Response,
    db: Db,
) -> CodexLoginResponse:
    settings: Settings = request.app.state.settings
    client_key = request.client.host if request.client else "unknown"
    enforce_rate_limit(
        db,
        settings=settings,
        action="codex_login",
        client_key=client_key,
    )
    try:
        attempt = request.app.state.codex_auth_bridge.start_login()
    except CodexAuthError as exc:
        raise ApiError("CODEX_AUTH_UNAVAILABLE", str(exc), 503) from exc
    if attempt.status == "authenticated" and attempt.account:
        _complete_codex_login(
            account=attempt.account,
            request=request,
            response=response,
            db=db,
        )
    return _codex_login_response(attempt)


@router.get("/auth/codex/status", response_model=CodexLoginResponse)
def codex_login_status(
    request: Request,
    response: Response,
    db: Db,
    attempt_id: Annotated[str, Query(min_length=36, max_length=36)],
) -> CodexLoginResponse:
    try:
        attempt = request.app.state.codex_auth_bridge.login_status(attempt_id)
    except CodexAuthError as exc:
        raise ApiError("CODEX_LOGIN_INVALID", str(exc), 400) from exc
    if attempt.status == "authenticated" and attempt.account:
        _complete_codex_login(
            account=attempt.account,
            request=request,
            response=response,
            db=db,
        )
    return _codex_login_response(attempt)


@router.post("/auth/invite-login", response_model=AuthResponse)
def invite_login(
    body: InviteLoginRequest, request: Request, response: Response, db: Db
) -> AuthResponse:
    settings: Settings = request.app.state.settings
    client_key = request.client.host if request.client else "unknown"
    enforce_rate_limit(
        db,
        settings=settings,
        action="invite_login",
        client_key=client_key,
    )
    candidate_hash = secret_hash(body.invite_code)
    user = db.scalar(select(User).where(User.invite_code_hash == candidate_hash))
    beta_invite = db.scalar(select(BetaInvite).where(BetaInvite.code_hash == candidate_hash))
    now = datetime.now(UTC)
    beta_expiry = beta_invite.expires_at if beta_invite else None
    beta_valid = bool(
        beta_invite
        and beta_invite.status == "active"
        and beta_invite.use_count < beta_invite.max_uses
        and (
            beta_expiry is None
            or (beta_expiry if beta_expiry.tzinfo else beta_expiry.replace(tzinfo=UTC)) > now
        )
    )
    configured_hash = verify_invite_code(body.invite_code, settings.invite_code_values)
    invite_hash = candidate_hash if user or beta_valid else configured_hash
    if not invite_hash:
        record_audit(
            db,
            project_id=None,
            actor_id=None,
            action="invite_login",
            target_type="invite_code",
            target_id=None,
            result="invalid",
            trace_id=trace_id(request),
        )
        db.commit()
        raise ApiError("INVALID_INVITE_CODE", "邀请码无效，请检查后重试。", 401)

    if not user:
        user = User(display_name=body.display_name, invite_code_hash=invite_hash)
        db.add(user)
        try:
            db.flush()
            if beta_valid and beta_invite:
                beta_invite.use_count += 1
                if beta_invite.use_count >= beta_invite.max_uses:
                    beta_invite.status = "claimed"
        except IntegrityError:
            db.rollback()
            user = db.scalar(select(User).where(User.invite_code_hash == invite_hash))
            if not user:
                raise ApiError("INVITE_CLAIM_CONFLICT", "邀请码领取发生冲突，请重试。", 409)
    if user.display_name != body.display_name:
        record_audit(
            db,
            project_id=None,
            actor_id=user.id,
            action="invite_login",
            target_type="invite_code",
            target_id=None,
            result="claimed_by_another_name",
            trace_id=trace_id(request),
        )
        db.commit()
        raise ApiError("INVITE_CODE_ALREADY_CLAIMED", "该邀请码已被其他用户领取。", 409)

    opaque_token = new_session_token()
    expires_at = datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours)
    login_session = Session(
        token_hash=session_token_hash(opaque_token, settings.session_secret.get_secret_value()),
        user_id=user.id,
        expires_at=expires_at,
    )
    db.add(login_session)
    db.flush()
    record_audit(
        db,
        project_id=None,
        actor_id=user.id,
        action="invite_login",
        target_type="session",
        target_id=login_session.id,
        result="success",
        trace_id=trace_id(request),
    )
    db.commit()
    _set_session_cookie(response, settings, opaque_token)
    return AuthResponse(user=user)


@router.get("/auth/me", response_model=AuthResponse)
def me(request: Request, db: Db, user: CurrentUser) -> AuthResponse:
    quota = user.quota or {}
    if quota.get("auth_provider") == "codex":
        stored_name = quota.get("codex_display_name")
        if not isinstance(stored_name, str) or not stored_name.strip():
            try:
                account = request.app.state.codex_auth_bridge.read_account(refresh_token=False)
            except CodexAuthError:
                account = None
            expected_identity = secret_hash(f"codex:{account.email}") if account else None
            if account and user.invite_code_hash == expected_identity:
                stored_name = account.display_name
                user.quota = {**quota, "codex_display_name": stored_name}
        if (
            isinstance(stored_name, str)
            and stored_name.strip()
            and user.display_name != stored_name
        ):
            user.display_name = stored_name[:80]
        if db.is_modified(user):
            db.commit()
            db.refresh(user)
    return AuthResponse(user=user)


def _credential_response(item: CredentialRef) -> ModelCredentialResponse:
    return ModelCredentialResponse(
        id=item.id,
        project_id=item.project_id,
        provider=item.provider,
        model=item.model,
        scope=item.scope,
        masked_hint=item.masked_hint,
        status=item.status,
        expires_at=item.expires_at,
        verified_at=item.verified_at,
        last_used_at=item.last_used_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _quota_response(item: QuotaAccount) -> QuotaResponse:
    return QuotaResponse(
        plan=item.plan,
        granted_units=item.granted_units,
        consumed_units=item.consumed_units,
        reserved_units=item.reserved_units,
        remaining_units=remaining_quota(item),
    )


def _usage_response(item: UsageLedger) -> UsageLedgerResponse:
    return UsageLedgerResponse(
        id=item.id,
        project_id=item.project_id,
        task_id=item.task_id,
        credential_ref_id=item.credential_ref_id,
        operation=item.operation,
        provider=item.provider,
        model=item.model,
        source=item.source,
        prompt_tokens=item.prompt_tokens,
        completion_tokens=item.completion_tokens,
        total_tokens=item.total_tokens,
        quota_units=item.quota_units,
        estimated_cost_microusd=item.estimated_cost_microusd,
        pricing_configured=item.pricing_configured,
        status=item.status,
        trace_id=item.trace_id,
        created_at=item.created_at,
    )


def _cost_response(item: CostAuthorization) -> CostAuthorizationResponse:
    return CostAuthorizationResponse(
        id=item.id,
        project_id=item.project_id,
        credential_ref_id=item.credential_ref_id,
        operation=item.operation,
        provider=item.provider,
        model=item.model,
        source=item.source,
        estimated_input_tokens=item.estimated_input_tokens,
        estimated_output_tokens=item.estimated_output_tokens,
        estimated_quota_units=item.estimated_quota_units,
        estimated_cost_microusd=item.estimated_cost_microusd,
        pricing_configured=item.pricing_configured,
        requires_confirmation=item.requires_confirmation,
        status=item.status,
        expires_at=item.expires_at,
        confirmed_at=item.confirmed_at,
        consumed_at=item.consumed_at,
        created_at=item.created_at,
    )


@router.post(
    "/model-credentials",
    response_model=ModelCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
def connect_model_credential(
    body: ModelCredentialCreateRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> ModelCredentialResponse:
    settings: Settings = request.app.state.settings
    vault: SecretVault = request.app.state.secret_vault
    if body.project_id:
        owned_project(db, body.project_id, user.id)
    if body.expires_at:
        expiry = body.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= datetime.now(UTC):
            raise ApiError("CREDENTIAL_EXPIRY_INVALID", "凭证有效期必须晚于当前时间。", 422)
    api_key = body.api_key.get_secret_value().strip()
    if len(api_key) < 8 or any(character.isspace() for character in api_key):
        raise ApiError("CREDENTIAL_FORMAT_INVALID", "模型 Key 格式不正确。", 422)
    fingerprint = vault.fingerprint(api_key)
    duplicate = db.scalar(
        select(CredentialRef).where(
            CredentialRef.owner_id == user.id,
            CredentialRef.project_id == body.project_id,
            CredentialRef.provider == body.provider,
            CredentialRef.scope == body.scope,
            CredentialRef.fingerprint == fingerprint,
            CredentialRef.status.not_in({"revoked", "expired"}),
        )
    )
    if duplicate:
        raise ApiError("CREDENTIAL_ALREADY_CONNECTED", "这个模型 Key 已经连接。", 409)
    secret_ref = vault.store(owner_id=user.id, secret=api_key)
    credential = CredentialRef(
        owner_id=user.id,
        project_id=body.project_id,
        provider=body.provider,
        model=settings.ai_model,
        scope=body.scope,
        secret_ref=secret_ref,
        fingerprint=fingerprint,
        masked_hint=masked_hint(api_key),
        status="unverified",
        expires_at=body.expires_at,
    )
    db.add(credential)
    try:
        db.flush()
        record_audit(
            db,
            project_id=body.project_id,
            actor_id=user.id,
            action="model_credential_connected",
            target_type="credential_ref",
            target_id=credential.id,
            result="success",
            trace_id=trace_id(request),
        )
        db.commit()
    except Exception:
        db.rollback()
        vault.delete(secret_ref)
        raise
    return _credential_response(credential)


@router.get("/model-credentials", response_model=ModelCredentialListResponse)
def list_model_credentials(db: Db, user: CurrentUser) -> ModelCredentialListResponse:
    items = list(
        db.scalars(
            select(CredentialRef)
            .where(CredentialRef.owner_id == user.id)
            .order_by(CredentialRef.created_at.desc())
        )
    )
    now = datetime.now(UTC)
    changed = False
    for item in items:
        expiry = item.expires_at
        if (
            expiry
            and (expiry if expiry.tzinfo else expiry.replace(tzinfo=UTC)) <= now
            and item.status not in {"revoked", "expired"}
        ):
            item.status = "expired"
            changed = True
    if changed:
        db.commit()
    return ModelCredentialListResponse(items=[_credential_response(item) for item in items])


@router.post(
    "/model-credentials/{credential_id}/verify",
    response_model=ModelCredentialResponse,
)
def verify_model_credential(
    credential_id: str,
    body: CredentialVerifyRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> ModelCredentialResponse:
    if not body.confirm_test_charge:
        raise ApiError(
            "COST_CONFIRMATION_REQUIRED",
            "验证会向模型供应商发送一次极小请求，请先确认可能产生费用。",
            409,
        )
    provider, credential = provider_for_credential(
        db,
        settings=request.app.state.settings,
        vault=request.app.state.secret_vault,
        owner_id=user.id,
        credential_id=credential_id,
        project_id=None,
    )
    try:
        result = generate_with_retry(
            provider,
            user_input="请只返回连接验证结果。",
            config=PreviewConfig(
                title="模型连接验证",
                description="验证模型凭证可用性",
                input_label="验证输入",
                input_placeholder="验证",
                submit_label="验证",
                output_title="验证结果",
            ),
            max_attempts=request.app.state.settings.ai_max_attempts,
        )
    except ApiError:
        record_audit(
            db,
            project_id=credential.project_id,
            actor_id=user.id,
            action="model_credential_verified",
            target_type="credential_ref",
            target_id=credential.id,
            result="failed",
            trace_id=trace_id(request),
        )
        db.commit()
        raise
    credential.status = "verified"
    credential.verified_at = datetime.now(UTC)
    record_usage(
        db,
        settings=request.app.state.settings,
        owner_id=user.id,
        project_id=credential.project_id,
        task_id=None,
        credential=credential,
        operation="credential_verify",
        provider=result.provider,
        model=result.model,
        usage=result.usage,
        trace_id=trace_id(request),
    )
    record_audit(
        db,
        project_id=credential.project_id,
        actor_id=user.id,
        action="model_credential_verified",
        target_type="credential_ref",
        target_id=credential.id,
        result="success",
        trace_id=trace_id(request),
    )
    db.commit()
    return _credential_response(credential)


@router.post("/model-credentials/{credential_id}/revoke", response_model=OkResponse)
def revoke_model_credential(
    credential_id: str,
    body: CredentialRevokeRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> OkResponse:
    if not body.confirm:
        raise ApiError("CONFIRMATION_REQUIRED", "撤销模型凭证前需要明确确认。", 409)
    credential = owned_credential(
        db,
        credential_id=credential_id,
        owner_id=user.id,
        active_only=False,
    )
    if credential.status != "revoked":
        request.app.state.secret_vault.delete(credential.secret_ref)
        credential.status = "revoked"
        record_audit(
            db,
            project_id=credential.project_id,
            actor_id=user.id,
            action="model_credential_revoked",
            target_type="credential_ref",
            target_id=credential.id,
            result="success",
            trace_id=trace_id(request),
        )
        db.commit()
    return OkResponse()


def _cloud_credential_response(item: CredentialRef) -> CloudCredentialResponse:
    if not item.project_id:
        raise ApiError("CLOUD_CREDENTIAL_PROJECT_REQUIRED", "云凭证未绑定项目。", 500)
    return CloudCredentialResponse(
        id=item.id,
        project_id=item.project_id,
        provider=item.provider,
        service=item.model,
        scope=item.scope,
        masked_access_key=item.masked_hint,
        status=item.status,
        expires_at=item.expires_at,
        created_at=item.created_at,
    )


@router.get("/cloud-credentials", response_model=CloudCredentialListResponse)
def list_cloud_credentials(
    project_id: str,
    db: Db,
    user: CurrentUser,
) -> CloudCredentialListResponse:
    owned_project(db, project_id, user.id)
    items = list(
        db.scalars(
            select(CredentialRef)
            .where(
                CredentialRef.owner_id == user.id,
                CredentialRef.project_id == project_id,
                CredentialRef.provider == "volcano_engine",
                CredentialRef.scope == "deployment",
            )
            .order_by(CredentialRef.created_at.desc())
        )
    )
    return CloudCredentialListResponse(items=[_cloud_credential_response(item) for item in items])


@router.post(
    "/cloud-credentials",
    response_model=CloudCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
def connect_cloud_credential(
    body: CloudCredentialCreateRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> CloudCredentialResponse:
    settings: Settings = request.app.state.settings
    if not settings.deployment_enabled:
        raise ApiError("DEPLOYMENT_DISABLED", "正式部署能力当前未启用。", 409)
    owned_project(db, body.project_id, user.id)
    if body.expires_at:
        expiry = body.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= datetime.now(UTC):
            raise ApiError("CREDENTIAL_EXPIRY_INVALID", "凭证有效期必须晚于当前时间。", 422)
    access_key = body.access_key_id.get_secret_value().strip()
    secret_key = body.secret_access_key.get_secret_value().strip()
    if any(character.isspace() or ord(character) < 33 for character in access_key + secret_key):
        raise ApiError("CREDENTIAL_FORMAT_INVALID", "云账号凭证格式不正确。", 422)
    vault: SecretVault = request.app.state.secret_vault
    fingerprint = vault.fingerprint(f"{access_key}:{secret_key}")
    duplicate = db.scalar(
        select(CredentialRef).where(
            CredentialRef.owner_id == user.id,
            CredentialRef.project_id == body.project_id,
            CredentialRef.provider == "volcano_engine",
            CredentialRef.scope == "deployment",
            CredentialRef.fingerprint == fingerprint,
            CredentialRef.status.not_in({"revoked", "expired"}),
        )
    )
    if duplicate:
        raise ApiError("CREDENTIAL_ALREADY_CONNECTED", "这个云账号凭证已经连接。", 409)
    secret_ref = vault.store(
        owner_id=user.id,
        secret=json.dumps(
            {"access_key_id": access_key, "secret_access_key": secret_key},
            ensure_ascii=False,
        ),
    )
    credential = CredentialRef(
        owner_id=user.id,
        project_id=body.project_id,
        provider="volcano_engine",
        model="vefaas",
        scope="deployment",
        secret_ref=secret_ref,
        fingerprint=fingerprint,
        masked_hint=masked_hint(access_key),
        status="unverified",
        expires_at=body.expires_at,
    )
    db.add(credential)
    try:
        db.flush()
        record_audit(
            db,
            project_id=body.project_id,
            actor_id=user.id,
            action="cloud_credential_connected",
            target_type="credential_ref",
            target_id=credential.id,
            result="stored_encrypted",
            trace_id=trace_id(request),
        )
        db.commit()
    except Exception:
        db.rollback()
        vault.delete(secret_ref)
        raise
    return _cloud_credential_response(credential)


@router.post("/cloud-credentials/{credential_id}/revoke", response_model=OkResponse)
def revoke_cloud_credential(
    credential_id: str,
    body: CredentialRevokeRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> OkResponse:
    if not body.confirm:
        raise ApiError("CONFIRMATION_REQUIRED", "撤销云凭证前需要明确确认。", 409)
    credential = owned_credential(
        db, credential_id=credential_id, owner_id=user.id, active_only=False
    )
    if credential.provider != "volcano_engine" or credential.scope != "deployment":
        raise not_found("云凭证")
    if credential.status != "revoked":
        request.app.state.secret_vault.delete(credential.secret_ref)
        credential.status = "revoked"
        record_audit(
            db,
            project_id=credential.project_id,
            actor_id=user.id,
            action="cloud_credential_revoked",
            target_type="credential_ref",
            target_id=credential.id,
            result="success",
            trace_id=trace_id(request),
        )
        db.commit()
    return OkResponse()


@router.get("/usage/quota", response_model=QuotaResponse)
def get_quota(request: Request, db: Db, user: CurrentUser) -> QuotaResponse:
    account = ensure_quota_account(db, user_id=user.id, settings=request.app.state.settings)
    db.commit()
    return _quota_response(account)


@router.get("/usage/ledger", response_model=UsageLedgerListResponse)
def list_usage_ledger(
    db: Db,
    user: CurrentUser,
    project_id: str | None = Query(default=None),
) -> UsageLedgerListResponse:
    if project_id:
        owned_project(db, project_id, user.id)
    statement = select(UsageLedger).where(UsageLedger.owner_id == user.id)
    if project_id:
        statement = statement.where(UsageLedger.project_id == project_id)
    items = list(db.scalars(statement.order_by(UsageLedger.created_at.desc()).limit(100)))
    return UsageLedgerListResponse(items=[_usage_response(item) for item in items])


@router.get("/usage/summary", response_model=UsageSummaryResponse)
def get_usage_summary(
    request: Request,
    db: Db,
    user: CurrentUser,
) -> UsageSummaryResponse:
    account = ensure_quota_account(db, user_id=user.id, settings=request.app.state.settings)
    totals = db.execute(
        select(
            func.coalesce(func.sum(UsageLedger.total_tokens), 0),
            func.coalesce(func.sum(UsageLedger.quota_units), 0),
            func.coalesce(func.sum(UsageLedger.estimated_cost_microusd), 0),
        ).where(UsageLedger.owner_id == user.id)
    ).one()
    priced_count = int(
        db.scalar(
            select(func.count(UsageLedger.id)).where(
                UsageLedger.owner_id == user.id,
                UsageLedger.pricing_configured.is_(True),
            )
        )
        or 0
    )
    db.commit()
    return UsageSummaryResponse(
        quota=_quota_response(account),
        total_tokens=int(totals[0] or 0),
        platform_quota_units=int(totals[1] or 0),
        estimated_cost_microusd=int(totals[2] or 0),
        pricing_configured=priced_count > 0,
    )


@router.post(
    "/projects/{project_id}/cost-quotes",
    response_model=CostAuthorizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def quote_project_cost(
    project_id: str,
    body: CostQuoteRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> CostAuthorizationResponse:
    project = owned_project(db, project_id, user.id)
    credential = None
    if body.credential_id:
        credential = owned_credential(
            db,
            credential_id=body.credential_id,
            owner_id=user.id,
            project_id=project.id,
        )
    item = create_cost_authorization(
        db,
        settings=request.app.state.settings,
        owner_id=user.id,
        project=project,
        operation=body.operation,
        credential=credential,
    )
    record_audit(
        db,
        project_id=project.id,
        actor_id=user.id,
        action="cost_quote_created",
        target_type="cost_authorization",
        target_id=item.id,
        result="success",
        trace_id=trace_id(request),
    )
    db.commit()
    return _cost_response(item)


@router.post(
    "/cost-authorizations/{authorization_id}/confirm",
    response_model=CostAuthorizationResponse,
)
def confirm_project_cost(
    authorization_id: str,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> CostAuthorizationResponse:
    item = owned_cost_authorization(
        db,
        authorization_id=authorization_id,
        owner_id=user.id,
    )
    if item.status == "expired":
        db.commit()
        raise ApiError("COST_QUOTE_EXPIRED", "费用预估已过期，请重新获取。", 409)
    if item.status == "pending":
        item.status = "confirmed"
        item.confirmed_at = datetime.now(UTC)
        record_audit(
            db,
            project_id=item.project_id,
            actor_id=user.id,
            action="cost_confirmed",
            target_type="cost_authorization",
            target_id=item.id,
            result="success",
            trace_id=trace_id(request),
        )
        db.commit()
    return _cost_response(item)


@router.post("/auth/logout", response_model=OkResponse)
def logout(request: Request, response: Response, db: Db, user: CurrentUser) -> OkResponse:
    settings: Settings = request.app.state.settings
    is_codex_user = (user.quota or {}).get("auth_provider") == "codex"
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        digest = session_token_hash(token, settings.session_secret.get_secret_value())
        login_session = db.scalar(select(Session).where(Session.token_hash == digest))
        if login_session:
            db.delete(login_session)
    record_audit(
        db,
        project_id=None,
        actor_id=user.id,
        action="logout",
        target_type="session",
        target_id=None,
        result="success",
        trace_id=trace_id(request),
    )
    db.commit()
    if is_codex_user:
        request.app.state.codex_auth_bridge.logout()
    response.delete_cookie(settings.session_cookie_name, path="/", samesite="lax")
    return OkResponse()


@router.get("/projects", response_model=ProjectListResponse)
def list_projects(db: Db, user: CurrentUser) -> ProjectListResponse:
    projects = list(
        db.scalars(
            select(Project)
            .where(
                Project.owner_id == user.id,
                Project.status != ProjectStatus.DELETED.value,
            )
            .order_by(Project.updated_at.desc(), Project.created_at.desc())
        )
    )
    return ProjectListResponse(items=[project_summary(db, project) for project in projects])


@router.post("/projects", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
def create_project_route(
    body: ProjectCreateRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> ProjectDetail:
    project_count = len(
        list(
            db.scalars(
                select(Project.id).where(
                    Project.owner_id == user.id,
                    Project.status != ProjectStatus.DELETED.value,
                )
            )
        )
    )
    if project_count >= int(user.quota.get("projects", 10)):
        raise ApiError("PROJECT_QUOTA_EXCEEDED", "已达到当前项目数量上限。", 403)
    project = create_project(db, owner_id=user.id, name=body.name, idea=body.idea)
    record_audit(
        db,
        project_id=project.id,
        actor_id=user.id,
        action="project_created",
        target_type="project",
        target_id=project.id,
        result="success",
        trace_id=trace_id(request),
    )
    db.commit()
    return project_detail(db, project)


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, db: Db, user: CurrentUser) -> ProjectDetail:
    return project_detail(db, owned_project(db, project_id, user.id))


@router.delete("/projects/{project_id}", response_model=OkResponse)
def delete_project(
    project_id: str,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> OkResponse:
    project = owned_project(db, project_id, user.id, lock=True)
    project.status = ProjectStatus.DELETED.value
    record_audit(
        db,
        project_id=project.id,
        actor_id=user.id,
        action="project_deleted",
        target_type="project",
        target_id=project_id,
        result="success",
        trace_id=trace_id(request),
    )
    db.commit()
    return OkResponse()


def _requirement_result(db: Db, project: Project, artifact: Artifact | None) -> RequirementResponse:
    db.commit()
    if artifact is None:
        detail = project_detail(db, project)
        questions = detail.next_action.questions
        return RequirementResponse(
            project=detail,
            status="question",
            reply="已记录这项信息。为了让首版范围可以验收，请继续回答下一个问题。",
            questions=questions,
            artifact=None,
        )
    return RequirementResponse(
        project=project_detail(db, project),
        status="prd_ready",
        reply="需求信息已整理为版本化 PRD。请先检查产品范围和验收标准，再确认或提出修改。",
        questions=[],
        artifact=artifact_response(artifact),
    )


_CODEX_WELCOME = CodexConversationMessage(
    id="welcome",
    role="assistant",
    content="把你的产品想法告诉我。我会一次只确认一个关键问题，并在右侧持续整理成 PRD。",
)


def _codex_conversation_state(project: Project) -> dict:
    requirement = project.requirement_session
    answers = requirement.answers_json if requirement is not None else {}
    raw_state = answers.get("codex") if isinstance(answers, dict) else None
    state = raw_state if isinstance(raw_state, dict) else {}
    conversation_id = state.get("id")
    if not isinstance(conversation_id, str) or not conversation_id:
        conversation_id = f"legacy-{requirement.id if requirement is not None else project.id}"
    thread_id = state.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id:
        thread_id = None
    messages: list[CodexConversationMessage] = []
    raw_messages = state.get("messages")
    if isinstance(raw_messages, list):
        for item in raw_messages:
            if not isinstance(item, dict):
                continue
            try:
                messages.append(CodexConversationMessage.model_validate(item))
            except ValueError:
                continue
    if not messages:
        messages = [_CODEX_WELCOME]
    draft = state.get("draft")
    if isinstance(draft, dict):
        try:
            draft = PrdContent.model_validate(draft).model_dump(mode="json")
        except ValueError:
            pass
    current_question = state.get("current_question")
    title = state.get("title")
    if not isinstance(title, str) or not title.strip():
        title = _codex_conversation_title(messages)
    created_at = _codex_timestamp(state.get("created_at"), project.created_at)
    updated_at = _codex_timestamp(state.get("updated_at"), project.updated_at)
    context_mode = state.get("context_mode")
    if context_mode not in {"project", "fresh"}:
        context_mode = "project"
    return {
        "id": conversation_id,
        "title": title,
        "thread_id": thread_id,
        "messages": [item.model_dump(mode="json") for item in messages],
        "draft": draft if isinstance(draft, dict) else None,
        "current_question": current_question if isinstance(current_question, dict) else None,
        "context_mode": context_mode,
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
    }


def _codex_timestamp(value: object, fallback: datetime) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return fallback


def _codex_conversation_title(messages: list[CodexConversationMessage]) -> str:
    first_user_message = next(
        (item.content.strip() for item in messages if item.role == "user" and item.content.strip()),
        "",
    )
    if not first_user_message:
        return "新对话"
    return first_user_message


def _codex_serialized_messages(state: dict) -> list[CodexConversationMessage]:
    messages: list[CodexConversationMessage] = []
    for item in state.get("messages", []):
        try:
            messages.append(CodexConversationMessage.model_validate(item))
        except (TypeError, ValueError):
            continue
    return messages or [_CODEX_WELCOME]


def _codex_history(project: Project) -> list[dict]:
    requirement = project.requirement_session
    answers = requirement.answers_json if requirement is not None else {}
    raw_history = answers.get("codex_history") if isinstance(answers, dict) else None
    if not isinstance(raw_history, list):
        return []
    return [
        item for item in raw_history if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]


def _codex_summary(state: dict, *, active: bool) -> CodexConversationSummary:
    messages = _codex_serialized_messages(state)
    return CodexConversationSummary(
        id=state["id"],
        title=state.get("title") or _codex_conversation_title(messages),
        active=active,
        message_count=sum(item.role == "user" for item in messages),
        created_at=_codex_timestamp(state.get("created_at"), datetime.now(UTC)),
        updated_at=_codex_timestamp(state.get("updated_at"), datetime.now(UTC)),
    )


def _codex_response(project: Project, db: Db, state: dict) -> CodexConversationResponse:
    return CodexConversationResponse(
        project=project_detail(db, project),
        conversation_id=state["id"],
        title=state["title"],
        thread_id=state.get("thread_id"),
        messages=_codex_serialized_messages(state),
        draft=state.get("draft"),
        current_question=state.get("current_question"),
    )


@router.get(
    "/projects/{project_id}/codex/conversation",
    response_model=CodexConversationResponse,
)
def codex_conversation(
    project_id: str,
    db: Db,
    user: CurrentUser,
) -> CodexConversationResponse:
    project = owned_project(db, project_id, user.id)
    return _codex_response(project, db, _codex_conversation_state(project))


@router.get(
    "/projects/{project_id}/codex/conversations",
    response_model=CodexConversationListResponse,
)
def codex_conversations(
    project_id: str,
    db: Db,
    user: CurrentUser,
) -> CodexConversationListResponse:
    project = owned_project(db, project_id, user.id)
    active = _codex_conversation_state(project)
    history = sorted(
        _codex_history(project),
        key=lambda item: _codex_timestamp(item.get("updated_at"), project.updated_at),
        reverse=True,
    )
    return CodexConversationListResponse(
        items=[
            _codex_summary(active, active=True),
            *[_codex_summary(item, active=False) for item in history],
        ],
    )


@router.post(
    "/projects/{project_id}/codex/conversations",
    response_model=CodexConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_codex_conversation(
    project_id: str,
    db: Db,
    user: CurrentUser,
) -> CodexConversationResponse:
    project = owned_project(db, project_id, user.id, lock=True)
    requirement = project.requirement_session
    if requirement is None:
        raise ApiError("REQUIREMENT_SESSION_MISSING", "需求会话无法恢复，请联系管理员。", 500)
    active = _codex_conversation_state(project)
    history = _codex_history(project)
    if active.get("thread_id") or any(
        item.role == "user" for item in _codex_serialized_messages(active)
    ):
        history = [active, *[item for item in history if item.get("id") != active["id"]]]
    now = datetime.now(UTC).isoformat()
    new_state = {
        "id": str(uuid4()),
        "title": "新对话",
        "thread_id": None,
        "messages": [_CODEX_WELCOME.model_dump(mode="json")],
        "draft": None,
        "current_question": None,
        "context_mode": "fresh",
        "created_at": now,
        "updated_at": now,
    }
    answers = deepcopy(requirement.answers_json)
    answers["codex"] = new_state
    answers["codex_history"] = history[:50]
    requirement.answers_json = answers
    db.commit()
    return _codex_response(project, db, new_state)


@router.post(
    "/projects/{project_id}/codex/conversations/{conversation_id}/activate",
    response_model=CodexConversationResponse,
)
def activate_codex_conversation(
    project_id: str,
    conversation_id: str,
    db: Db,
    user: CurrentUser,
) -> CodexConversationResponse:
    project = owned_project(db, project_id, user.id, lock=True)
    requirement = project.requirement_session
    if requirement is None:
        raise ApiError("REQUIREMENT_SESSION_MISSING", "需求会话无法恢复，请联系管理员。", 500)
    active = _codex_conversation_state(project)
    if conversation_id == active["id"]:
        return _codex_response(project, db, active)
    history = _codex_history(project)
    selected = next((item for item in history if item.get("id") == conversation_id), None)
    if selected is None:
        raise not_found("历史对话")
    remaining = [item for item in history if item.get("id") != conversation_id]
    if active.get("thread_id") or any(
        item.role == "user" for item in _codex_serialized_messages(active)
    ):
        remaining.insert(0, active)
    answers = deepcopy(requirement.answers_json)
    answers["codex"] = selected
    answers["codex_history"] = remaining[:50]
    requirement.answers_json = answers
    db.commit()
    return _codex_response(project, db, selected)


@router.get(
    "/projects/{project_id}/codex/reasoning/{progress_id}",
    response_model=CodexReasoningProgressResponse,
)
def codex_reasoning_progress(
    project_id: str,
    progress_id: str,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> CodexReasoningProgressResponse:
    project = owned_project(db, project_id, user.id)
    progress = request.app.state.codex_reasoning_progress.read(
        progress_id,
        owner_id=user.id,
        project_id=project.id,
    )
    if progress is None:
        return CodexReasoningProgressResponse(status="pending", summary="")
    return CodexReasoningProgressResponse(status=progress.status, summary=progress.summary)


@router.post(
    "/projects/{project_id}/codex/messages",
    response_model=CodexRequirementResponse,
)
def codex_requirement_message(
    project_id: str,
    body: RequirementMessageRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> CodexRequirementResponse:
    project = owned_project(db, project_id, user.id, lock=True)
    if project.stage not in {
        ProjectStage.REQUIREMENTS.value,
        ProjectStage.PRD_REVIEW.value,
    }:
        raise ApiError("INVALID_PROJECT_STAGE", "当前阶段不能继续补充需求。", 409)
    requirement = project.requirement_session
    if requirement is None:
        raise ApiError("REQUIREMENT_SESSION_MISSING", "需求会话无法恢复，请联系管理员。", 500)

    state = _codex_conversation_state(project)
    thread_id = state.get("thread_id")
    messages = _codex_serialized_messages(state)
    conversation_id = state["id"]
    pending_user_id = f"pending:{uuid4()}"
    pending_messages = [
        *messages,
        CodexConversationMessage(id=pending_user_id, role="user", content=body.message),
    ]
    pending_answers = deepcopy(requirement.answers_json)
    pending_answers["codex"] = {
        **state,
        "title": _codex_conversation_title(pending_messages),
        "messages": [item.model_dump(mode="json") for item in pending_messages],
        "updated_at": datetime.now(UTC).isoformat(),
    }
    requirement.answers_json = pending_answers
    db.commit()
    progress_id = body.progress_id
    progress_store = request.app.state.codex_reasoning_progress
    if progress_id:
        progress_store.start(progress_id, owner_id=user.id, project_id=project.id)
    try:
        result = run_codex_requirement_turn(
            request.app.state.codex_auth_bridge,
            project,
            message=body.message,
            thread_id=thread_id,
            workspace=request.app.state.settings.workspace_root / project.id,
            on_reasoning_summary=(
                (lambda delta: progress_store.append(progress_id, delta)) if progress_id else None
            ),
            model=body.model,
            reasoning_effort=body.reasoning_effort,
            include_project_idea=state.get("context_mode") != "fresh",
        )
    except CodexAuthError as exc:
        if progress_id:
            progress_store.finish(progress_id, status="failed")
        raise ApiError("CODEX_UNAVAILABLE", str(exc), 503) from exc

    db.refresh(project)
    db.refresh(requirement)
    messages = [
        *messages,
        CodexConversationMessage(
            id=f"{result.turn_id}:user",
            role="user",
            content=body.message,
        ),
        CodexConversationMessage(
            id=f"{result.turn_id}:assistant",
            role="assistant",
            content=result.reply,
        ),
    ]
    answers = deepcopy(requirement.answers_json)
    now = datetime.now(UTC).isoformat()
    draft_payload = result.prd.model_dump(mode="json") if result.prd else None
    updated_state = {
        "id": conversation_id,
        "title": _codex_conversation_title(messages),
        "thread_id": result.thread_id,
        "messages": [item.model_dump(mode="json") for item in messages],
        "draft": draft_payload,
        "current_question": result.question.model_dump(mode="json") if result.question else None,
        "context_mode": state.get("context_mode", "project"),
        "created_at": state["created_at"],
        "updated_at": now,
    }
    active_state = answers.get("codex") if isinstance(answers, dict) else None
    if isinstance(active_state, dict) and active_state.get("id") == conversation_id:
        answers["codex"] = updated_state
    else:
        history = answers.get("codex_history") if isinstance(answers, dict) else None
        history_items = (
            [item for item in history if isinstance(item, dict)]
            if isinstance(history, list)
            else []
        )
        answers["codex_history"] = [
            updated_state,
            *[item for item in history_items if item.get("id") != conversation_id],
        ][:50]
    answers.setdefault("messages", []).append(
        {
            "role": "user",
            "content": body.message,
            "kind": "codex_message",
            "turn_id": result.turn_id,
        }
    )
    requirement.answers_json = answers
    requirement.round += 1

    artifact = None
    if result.prd_ready:
        if result.prd is None:
            raise ApiError("CODEX_INVALID_OUTPUT", "Codex 未返回完整 PRD，请重试。", 503)
        artifact = create_prd_artifact_from_content(db, project, result.prd)
        requirement.missing_items_json = []
        if project.stage == ProjectStage.REQUIREMENTS.value:
            transition(project, ProjectStage.PRD_REVIEW.value)

    db.flush()
    record_audit(
        db,
        project_id=project.id,
        actor_id=user.id,
        action="codex_requirement_turn_completed",
        target_type="artifact" if artifact else "requirement_session",
        target_id=artifact.id if artifact else requirement.id,
        result="success",
        trace_id=trace_id(request),
    )
    db.commit()
    if progress_id:
        progress_store.finish(progress_id, status="completed")
    return CodexRequirementResponse(
        project=project_detail(db, project),
        conversation_id=updated_state["id"],
        title=updated_state["title"],
        thread_id=result.thread_id,
        messages=messages,
        draft=draft_payload,
        status="prd_ready" if artifact else "question",
        reply=result.reply,
        current_question=result.question.model_dump(mode="json") if result.question else None,
        artifact=artifact_response(artifact) if artifact else None,
    )


@router.post("/projects/{project_id}/requirements/messages", response_model=RequirementResponse)
def requirement_message(
    project_id: str,
    body: RequirementMessageRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> RequirementResponse:
    project = owned_project(db, project_id, user.id, lock=True)
    artifact = ingest_requirement(
        db,
        project,
        body.message,
        question_id=body.question_id,
        provider=request.app.state.provider,
        max_attempts=request.app.state.settings.ai_max_attempts,
    )
    db.flush()
    record_audit(
        db,
        project_id=project.id,
        actor_id=user.id,
        action="requirement_submitted",
        target_type="artifact" if artifact else "requirement_session",
        target_id=artifact.id if artifact else project.requirement_session.id,
        result="success",
        trace_id=trace_id(request),
    )
    return _requirement_result(db, project, artifact)


@router.post("/projects/{project_id}/requirements/upload", response_model=RequirementResponse)
def requirement_upload(
    project_id: str,
    request: Request,
    db: Db,
    user: CurrentUser,
    file: Annotated[UploadFile, File(...)],
) -> RequirementResponse:
    settings: Settings = request.app.state.settings
    try:
        content = file.file.read(settings.max_upload_bytes + 1)
    finally:
        file.file.close()
    text = extract_upload_text(file, content, settings)
    project = owned_project(db, project_id, user.id, lock=True)
    artifact = ingest_requirement(
        db,
        project,
        text,
        kind="upload",
        provider=request.app.state.provider,
        max_attempts=request.app.state.settings.ai_max_attempts,
    )
    db.flush()
    record_audit(
        db,
        project_id=project.id,
        actor_id=user.id,
        action="requirements_uploaded",
        target_type="artifact" if artifact else "requirement_session",
        target_id=artifact.id if artifact else project.requirement_session.id,
        result="success",
        trace_id=trace_id(request),
    )
    return _requirement_result(db, project, artifact)


@router.get("/projects/{project_id}/artifacts", response_model=ArtifactListResponse)
def list_artifacts(
    project_id: str,
    db: Db,
    user: CurrentUser,
    artifact_type: str | None = Query(default=None, alias="type"),
) -> ArtifactListResponse:
    owned_project(db, project_id, user.id)
    if artifact_type and artifact_type not in {
        ArtifactType.PRD.value,
        ArtifactType.SOLUTION.value,
        ArtifactType.FAILURE_REPORT.value,
        ArtifactType.CHANGE_REQUEST.value,
    }:
        raise ApiError("INVALID_ARTIFACT_TYPE", "产物类型不受支持。", 422)
    statement = select(Artifact).where(Artifact.project_id == project_id)
    if artifact_type:
        statement = statement.where(Artifact.type == artifact_type)
    items = list(db.scalars(statement.order_by(Artifact.type, Artifact.version.desc())))
    return ArtifactListResponse(items=[artifact_response(item) for item in items])


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
def get_artifact(artifact_id: str, db: Db, user: CurrentUser) -> ArtifactResponse:
    artifact = db.scalar(
        select(Artifact)
        .join(Project, Project.id == Artifact.project_id)
        .where(
            Artifact.id == artifact_id,
            Project.owner_id == user.id,
            Project.status != ProjectStatus.DELETED.value,
        )
    )
    if not artifact:
        raise not_found("产物")
    return artifact_response(artifact)


def _confirm(
    *,
    project_id: str,
    artifact_type: str,
    body: ConfirmationRequest,
    request: Request,
    db: Db,
    user: User,
) -> ConfirmationActionResponse:
    project = owned_project(db, project_id, user.id, lock=True)
    artifact = db.scalar(
        select(Artifact).where(
            Artifact.id == body.artifact_id,
            Artifact.project_id == project.id,
        )
    )
    if not artifact:
        raise not_found("产物")
    try:
        confirmation, next_artifact = confirm_artifact(
            db,
            project=project,
            artifact=artifact,
            artifact_type=artifact_type,
            decision=body.decision,
            comment=body.comment,
            provider=request.app.state.provider,
            max_attempts=request.app.state.settings.ai_max_attempts,
        )
        db.flush()
        record_audit(
            db,
            project_id=project.id,
            actor_id=user.id,
            action=f"{artifact_type}_{body.decision}",
            target_type="artifact",
            target_id=artifact.id,
            result="success",
            trace_id=trace_id(request),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        project = owned_project(db, project_id, user.id)
        artifact = db.scalar(
            select(Artifact).where(
                Artifact.id == body.artifact_id,
                Artifact.project_id == project.id,
            )
        )
        if not artifact:
            raise not_found("产物")
        confirmation = db.scalar(
            select(Confirmation).where(
                Confirmation.artifact_id == artifact.id,
                Confirmation.decision == body.decision,
            )
        )
        if not confirmation:
            raise ApiError("CONFIRMATION_CONFLICT", "确认发生并发冲突，请刷新后重试。", 409)
        if body.decision == "revise":
            next_artifact = latest_artifact(db, project.id, artifact_type)
        elif artifact_type == ArtifactType.PRD.value:
            next_artifact = latest_artifact(db, project.id, ArtifactType.SOLUTION.value)
        else:
            next_artifact = None
    return ConfirmationActionResponse(
        project=project_detail(db, project),
        artifact=artifact_response(artifact),
        confirmation=confirmation_response(confirmation) if confirmation else None,
        next_artifact=artifact_response(next_artifact) if next_artifact else None,
    )


@router.post("/projects/{project_id}/confirmations/prd", response_model=ConfirmationActionResponse)
def confirm_prd(
    project_id: str,
    body: ConfirmationRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> ConfirmationActionResponse:
    return _confirm(
        project_id=project_id,
        artifact_type=ArtifactType.PRD.value,
        body=body,
        request=request,
        db=db,
        user=user,
    )


@router.post(
    "/projects/{project_id}/confirmations/solution", response_model=ConfirmationActionResponse
)
def confirm_solution(
    project_id: str,
    body: ConfirmationRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> ConfirmationActionResponse:
    return _confirm(
        project_id=project_id,
        artifact_type=ArtifactType.SOLUTION.value,
        body=body,
        request=request,
        db=db,
        user=user,
    )


@router.post("/projects/{project_id}/development/start", response_model=TaskResponse)
def start_development(
    project_id: str,
    request: Request,
    db: Db,
    user: CurrentUser,
    body: DevelopmentStartRequest | None = None,
) -> TaskResponse:
    body = body or DevelopmentStartRequest()
    project = owned_project(db, project_id, user.id, lock=True)
    try:
        task, created = start_development_task(
            db,
            project=project,
            trace_id=trace_id(request),
            settings=request.app.state.settings,
            ui_style_key=body.ui_style_key,
        )
        if created:
            credential = None
            if body.credential_id:
                credential = owned_credential(
                    db,
                    credential_id=body.credential_id,
                    owner_id=user.id,
                    project_id=project.id,
                )
                if credential.scope not in {"development", "both"}:
                    raise ApiError("CREDENTIAL_SCOPE_DENIED", "这个模型 Key 未授权用于开发。", 403)
                if credential.status != "verified":
                    raise ApiError("CREDENTIAL_NOT_VERIFIED", "请先验证模型 Key 再开始开发。", 409)
            if request.app.state.settings.ai_provider != "mock" and not body.cost_authorization_id:
                raise ApiError(
                    "COST_CONFIRMATION_REQUIRED",
                    "真实模型开发前必须先获取并确认预计用量和费用。",
                    409,
                )
            if body.cost_authorization_id:
                consume_authorization(
                    db,
                    authorization_id=body.cost_authorization_id,
                    owner_id=user.id,
                    project_id=project.id,
                    operation="development",
                    credential_id=credential.id if credential else None,
                )
                task.checkpoint_json = {
                    **task.checkpoint_json,
                    "cost_authorization_id": body.cost_authorization_id,
                }
            if credential:
                task.checkpoint_json = {
                    **task.checkpoint_json,
                    "credential_ref_id": credential.id,
                }
                task.budget_json = {**task.budget_json, "usage_source": "user_key"}
        if created:
            record_audit(
                db,
                project_id=project.id,
                actor_id=user.id,
                action="development_started",
                target_type="task",
                target_id=task.id,
                result="accepted",
                trace_id=trace_id(request),
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        project = owned_project(db, project_id, user.id)
        key = f"development:{project.id}:{project.development_revision}"
        task = db.scalar(select(Task).where(Task.idempotency_key == key))
        if not task:
            raise ApiError("TASK_START_CONFLICT", "任务启动冲突，请重试。", 409)
        created = False
    response = task_response(task)
    if created:
        request.app.state.task_runner.enqueue(task.id)
    return response


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Db, user: CurrentUser) -> TaskResponse:
    task = db.scalar(
        select(Task)
        .join(Project, Project.id == Task.project_id)
        .where(
            Task.id == task_id,
            Project.owner_id == user.id,
            Project.status != ProjectStatus.DELETED.value,
        )
    )
    if not task:
        raise not_found("任务")
    return task_response(task)


@router.get(
    "/projects/{project_id}/development-workspace",
    response_model=DevelopmentWorkspaceResponse,
)
def get_development_workspace(
    project_id: str,
    db: Db,
    user: CurrentUser,
) -> DevelopmentWorkspaceResponse:
    return workspace_response(owned_workspace(db, project_id, user.id))


@router.get(
    "/projects/{project_id}/development-runs",
    response_model=DevelopmentRunListResponse,
)
def list_development_runs(
    project_id: str,
    db: Db,
    user: CurrentUser,
) -> DevelopmentRunListResponse:
    owned_project(db, project_id, user.id)
    runs = list(
        db.scalars(
            select(DevelopmentRun)
            .where(DevelopmentRun.project_id == project_id)
            .order_by(DevelopmentRun.created_at.desc())
        )
    )
    return DevelopmentRunListResponse(items=[development_run_response(db, item) for item in runs])


@router.get(
    "/development-runs/{run_id}",
    response_model=DevelopmentRunResponse,
)
def get_development_run(
    run_id: str,
    db: Db,
    user: CurrentUser,
) -> DevelopmentRunResponse:
    return development_run_response(db, owned_development_run(db, run_id, user.id))


@router.get(
    "/projects/{project_id}/quality-history",
    response_model=QualityHistoryResponse,
)
def get_quality_history(
    project_id: str,
    db: Db,
    user: CurrentUser,
) -> QualityHistoryResponse:
    owned_project(db, project_id, user.id)
    quality_runs = list(
        db.scalars(
            select(QualityRun)
            .where(QualityRun.project_id == project_id)
            .order_by(QualityRun.started_at, QualityRun.sequence)
        )
    )
    repairs = list(
        db.scalars(
            select(RepairAttempt)
            .where(RepairAttempt.project_id == project_id)
            .order_by(RepairAttempt.created_at, RepairAttempt.attempt)
        )
    )
    return QualityHistoryResponse(
        quality_runs=[quality_run_response(item) for item in quality_runs],
        repair_attempts=[repair_attempt_response(item) for item in repairs],
    )


@router.get(
    "/code-versions/{code_version_id}/files/{file_path:path}",
    response_model=CodeFileContentResponse,
)
def get_code_version_file(
    code_version_id: str,
    file_path: str,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> CodeFileContentResponse:
    code_version = db.scalar(
        select(CodeVersion)
        .join(Project, Project.id == CodeVersion.project_id)
        .where(
            CodeVersion.id == code_version_id,
            Project.owner_id == user.id,
            Project.status != ProjectStatus.DELETED.value,
        )
    )
    if not code_version:
        raise not_found("代码版本")
    metadata = db.scalar(
        select(CodeFile).where(
            CodeFile.code_version_id == code_version.id,
            CodeFile.path == file_path,
        )
    )
    if not metadata:
        raise not_found("代码文件")
    try:
        content = read_file_at_commit(
            settings=request.app.state.settings,
            project_id=code_version.project_id,
            commit_ref=code_version.commit_ref,
            path=file_path,
        )
    except ControlledCodingError as exc:
        status_code = 404 if exc.code == "CODE_FILE_NOT_FOUND" else 409
        raise ApiError(exc.code, str(exc), status_code) from exc
    item = code_file_metadata(metadata)
    return CodeFileContentResponse(
        **item.model_dump(),
        commit_ref=code_version.commit_ref,
        content=content,
    )


@router.post("/tasks/{task_id}/retry", response_model=TaskResponse)
def retry_task(
    task_id: str,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> TaskResponse:
    failed_task = db.scalar(
        select(Task)
        .join(Project, Project.id == Task.project_id)
        .where(
            Task.id == task_id,
            Project.owner_id == user.id,
            Project.status != ProjectStatus.DELETED.value,
        )
    )
    if not failed_task:
        raise not_found("任务")
    project = owned_project(db, failed_task.project_id, user.id, lock=True)
    try:
        retry, created = retry_failed_task(
            db,
            failed_task=failed_task,
            project=project,
            trace_id=trace_id(request),
            settings=request.app.state.settings,
        )
        if created:
            record_audit(
                db,
                project_id=project.id,
                actor_id=user.id,
                action="development_task_retried",
                target_type="task",
                target_id=retry.id,
                result="accepted",
                trace_id=trace_id(request),
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        retry = db.scalar(select(Task).where(Task.idempotency_key == f"retry:{task_id}"))
        if not retry:
            raise ApiError("TASK_RETRY_CONFLICT", "任务恢复发生冲突，请重试。", 409)
        created = False
    response = task_response(retry)
    if created:
        request.app.state.task_runner.enqueue(retry.id)
    return response


@router.get("/tasks/{task_id}/events")
async def task_events(
    task_id: str,
    request: Request,
    db: Db,
    user: CurrentUser,
    after: int = Query(default=0, ge=0),
) -> StreamingResponse:
    task = db.scalar(
        select(Task)
        .join(Project, Project.id == Task.project_id)
        .where(
            Task.id == task_id,
            Project.owner_id == user.id,
            Project.status != ProjectStatus.DELETED.value,
        )
    )
    if not task:
        raise not_found("任务")
    header_value = request.headers.get("last-event-id")
    if header_value and header_value.isdigit():
        after = max(after, int(header_value))
    session_factory = request.app.state.database.session_factory

    async def stream():
        cursor = after
        while True:
            if await request.is_disconnected():
                return
            with session_factory() as event_db:
                current = event_db.get(Task, task_id)
                events = list(
                    event_db.scalars(
                        select(TaskEvent)
                        .where(TaskEvent.task_id == task_id, TaskEvent.sequence > cursor)
                        .order_by(TaskEvent.sequence)
                    )
                )
                for event in events:
                    cursor = event.sequence
                    if event.type == EventType.ERROR.value:
                        payload = {
                            "error": {
                                "code": event.payload_json.get("error_code", "TASK_FAILED"),
                                "message": event.message,
                                "trace_id": current.trace_id if current else None,
                            }
                        }
                        stream_event_type = EventType.ERROR.value
                    else:
                        payload = {
                            "id": event.id,
                            "task_id": event.task_id,
                            "sequence": event.sequence,
                            "type": event.type,
                            "message": event.message,
                            "payload": event.payload_json,
                            "created_at": event.created_at.isoformat(),
                        }
                        stream_event_type = (
                            EventType.DONE.value if event.type == EventType.DONE.value else "chunk"
                        )
                    yield (
                        f"id: {event.sequence}\n"
                        f"event: {stream_event_type}\n"
                        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    )
                    if event.type in {EventType.DONE.value, EventType.ERROR.value}:
                        return
                if current and current.status in {"succeeded", "failed"} and not events:
                    terminal = "done" if current.status == "succeeded" else "error"
                    if terminal == "error":
                        payload = {
                            "error": {
                                "code": current.error_code or "TASK_FAILED",
                                "message": "任务失败，最后检查点已保留。",
                                "trace_id": current.trace_id,
                            }
                        }
                    else:
                        payload = {
                            "task_id": current.id,
                            "sequence": cursor,
                            "type": terminal,
                            "message": "任务已结束，可通过任务详情恢复最终状态。",
                            "payload": {"status": current.status, "progress": current.progress},
                        }
                    yield f"event: {terminal}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    return
            await asyncio.sleep(0.1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _active_preview(
    db: Db,
    preview_token: str,
    user_id: str,
    preview_manager: object | None = None,
) -> Preview:
    preview = db.scalar(
        select(Preview)
        .join(Project, Project.id == Preview.project_id)
        .where(
            Preview.preview_token == preview_token,
            Project.owner_id == user_id,
            Project.status != ProjectStatus.DELETED.value,
        )
    )
    if not preview:
        raise not_found("预览")
    if preview.status == "expired":
        raise ApiError("PREVIEW_EXPIRED", "这个预览已过期。", 410)
    if preview.status != "ready":
        raise ApiError("PREVIEW_NOT_READY", "这个预览当前不可用。", 409)
    expires_at = preview.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        preview.status = "expired"
        runtime = db.scalar(select(PreviewRuntime).where(PreviewRuntime.preview_id == preview.id))
        if runtime:
            runtime.status = "expired"
            runtime.stopped_at = datetime.now(UTC)
            if preview_manager is not None:
                preview_manager.stop(runtime.process_ref)
        db.commit()
        raise ApiError("PREVIEW_EXPIRED", "这个预览已过期。", 410)
    return preview


def _preview_response(db: Db, preview: Preview) -> PreviewResponse:
    code_version = db.get(CodeVersion, preview.code_version_id)
    if not code_version:
        raise ApiError("CODE_VERSION_MISSING", "预览对应的代码版本不存在。", 500)
    runs = list(
        db.scalars(
            select(PreviewRun)
            .where(PreviewRun.preview_id == preview.id)
            .order_by(PreviewRun.created_at)
        )
    )
    return PreviewResponse(
        id=preview.id,
        token=preview.preview_token,
        project_id=preview.project_id,
        status=preview.status,
        url_path=preview.url_path,
        expires_at=preview.expires_at,
        code_version=code_version_response(code_version),
        config=preview.config_json,
        history=[preview_run_response(run) for run in runs],
    )


@router.get("/previews/{preview_token}", response_model=PreviewResponse)
def get_preview(
    preview_token: str,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> PreviewResponse:
    return _preview_response(
        db,
        _active_preview(db, preview_token, user.id, request.app.state.preview_manager),
    )


@router.post(
    "/previews/{preview_token}/acceptance",
    response_model=PreviewAcceptanceResponse,
)
def accept_preview(
    preview_token: str,
    body: PreviewAcceptanceRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> PreviewAcceptanceResponse:
    preview = _active_preview(db, preview_token, user.id, request.app.state.preview_manager)
    project = owned_project(db, preview.project_id, user.id, lock=True)
    checklist = body.model_dump()
    if not all(checklist.values()):
        raise ApiError("PREVIEW_CHECKLIST_INCOMPLETE", "请先完成全部核心验收项。", 409)
    existing = db.scalar(
        select(PreviewAcceptance).where(PreviewAcceptance.preview_id == preview.id)
    )
    if existing:
        return acceptance_response(existing)
    code_version = db.get(CodeVersion, preview.code_version_id)
    if not code_version or code_version.test_status != "quality_passed":
        raise ApiError("PREVIEW_VERSION_NOT_VERIFIED", "预览版本没有通过质量门。", 409)
    item = PreviewAcceptance(
        project_id=project.id,
        preview_id=preview.id,
        code_version_id=code_version.id,
        actor_id=user.id,
        decision="accepted",
        checklist_json=checklist,
    )
    db.add(item)
    try:
        db.flush()
        record_audit(
            db,
            project_id=project.id,
            actor_id=user.id,
            action="preview_accepted",
            target_type="preview",
            target_id=preview.id,
            result="success",
            trace_id=trace_id(request),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        item = db.scalar(
            select(PreviewAcceptance).where(PreviewAcceptance.preview_id == preview.id)
        )
        if not item:
            raise ApiError(
                "PREVIEW_ACCEPTANCE_CONFLICT", "预览验收发生冲突，请重试。", 409
            ) from None
    return acceptance_response(item)


def _runtime_for_preview(db: Db, preview: Preview) -> PreviewRuntime:
    runtime = db.scalar(select(PreviewRuntime).where(PreviewRuntime.preview_id == preview.id))
    if not runtime:
        raise ApiError("PREVIEW_RUNTIME_MISSING", "这个预览没有绑定生成应用运行环境。", 409)
    if runtime.status != "ready" or not runtime.base_url:
        raise ApiError("PREVIEW_RUNTIME_NOT_READY", "生成应用预览当前不可用。", 409)
    return runtime


@router.get(
    "/previews/{preview_token}/page",
    response_class=HTMLResponse,
)
def get_generated_product_page(
    preview_token: str,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> HTMLResponse:
    preview = _active_preview(db, preview_token, user.id, request.app.state.preview_manager)
    config = PreviewConfig.model_validate(preview.config_json)
    if config.template != "controlled_html_webapp_v1":
        raise ApiError("HTML_PREVIEW_NOT_AVAILABLE", "这个代码版本没有 HTML 产品页面。", 404)
    runtime = _runtime_for_preview(db, preview)
    try:
        response = request.app.state.preview_manager.request(
            process_ref=runtime.process_ref,
            base_url=runtime.base_url,
            method="GET",
            path="/",
        )
        if response.status_code != 200 or "text/html" not in response.headers.get(
            "content-type", ""
        ):
            raise QualityRuntimeError("HTML_PREVIEW_INVALID", "生成应用没有返回 HTML 页面。")
    except QualityRuntimeError as exc:
        raise ApiError("PREVIEW_UNAVAILABLE", "HTML 产品预览暂时不可用。", 503) from exc
    record_audit(
        db,
        project_id=preview.project_id,
        actor_id=user.id,
        action="generated_html_preview_opened",
        target_type="preview_runtime",
        target_id=runtime.id,
        result="success",
        trace_id=trace_id(request),
    )
    runtime.last_health_at = datetime.now(UTC)
    db.commit()
    return HTMLResponse(
        response.text,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                "img-src data:; font-src data:; connect-src 'self'; "
                "frame-ancestors http://localhost:3000 http://127.0.0.1:3000"
            ),
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/previews/{preview_token}/runtime",
    response_model=PreviewRuntimeResponse,
)
def get_preview_runtime(
    preview_token: str,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> PreviewRuntimeResponse:
    preview = _active_preview(db, preview_token, user.id, request.app.state.preview_manager)
    runtime = _runtime_for_preview(db, preview)
    try:
        response = request.app.state.preview_manager.request(
            process_ref=runtime.process_ref,
            base_url=runtime.base_url,
            method="GET",
            path="/api/v1/health",
        )
        health = response.json()
        if response.status_code != 200 or health.get("status") != "ok":
            raise QualityRuntimeError("PREVIEW_UNHEALTHY", "生成应用健康检查未通过。")
    except (QualityRuntimeError, ValueError) as exc:
        runtime.status = "failed"
        runtime.error_code = getattr(exc, "code", "PREVIEW_UNHEALTHY")
        preview.status = "failed"
        db.commit()
        raise ApiError("PREVIEW_UNAVAILABLE", "生成应用预览暂时不可用。", 503) from exc
    runtime.health_json = health
    runtime.last_health_at = datetime.now(UTC)
    db.commit()
    return preview_runtime_response(
        runtime,
        public_base_url=f"/api/v1/previews/{preview_token}/runtime",
    )


@router.post(
    "/previews/{preview_token}/runtime/analyze",
    response_model=RuntimeAnalyzeResponse,
)
def run_generated_preview(
    preview_token: str,
    body: PreviewRunRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> RuntimeAnalyzeResponse:
    preview = _active_preview(db, preview_token, user.id, request.app.state.preview_manager)
    runtime = _runtime_for_preview(db, preview)
    try:
        response = request.app.state.preview_manager.request(
            process_ref=runtime.process_ref,
            base_url=runtime.base_url,
            method="POST",
            path="/api/v1/analyze",
            json_body={"input": body.input},
        )
        if response.status_code != 200:
            raise QualityRuntimeError("GENERATED_APP_ERROR", "生成应用没有接受本次输入。")
        result = AgentResult.model_validate(response.json())
        history_response = request.app.state.preview_manager.request(
            process_ref=runtime.process_ref,
            base_url=runtime.base_url,
            method="GET",
            path="/api/v1/history",
        )
        history = history_response.json()
        if history_response.status_code != 200 or not isinstance(history, list):
            raise QualityRuntimeError("GENERATED_APP_HISTORY_ERROR", "生成应用历史记录不可用。")
    except (QualityRuntimeError, ValueError) as exc:
        raise ApiError(
            getattr(exc, "code", "GENERATED_APP_INVALID_OUTPUT"),
            "生成应用本次运行失败，请稍后重试。",
            502,
        ) from exc
    record_audit(
        db,
        project_id=preview.project_id,
        actor_id=user.id,
        action="generated_preview_run",
        target_type="preview_runtime",
        target_id=runtime.id,
        result="success",
        trace_id=trace_id(request),
    )
    db.commit()
    return RuntimeAnalyzeResponse(result=result, history_count=len(history))


@router.get(
    "/previews/{preview_token}/runtime/history",
    response_model=RuntimeHistoryResponse,
)
def get_generated_preview_history(
    preview_token: str,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> RuntimeHistoryResponse:
    preview = _active_preview(db, preview_token, user.id, request.app.state.preview_manager)
    runtime = _runtime_for_preview(db, preview)
    try:
        response = request.app.state.preview_manager.request(
            process_ref=runtime.process_ref,
            base_url=runtime.base_url,
            method="GET",
            path="/api/v1/history",
        )
        payload = response.json()
        if response.status_code != 200 or not isinstance(payload, list):
            raise QualityRuntimeError("GENERATED_APP_HISTORY_ERROR", "生成应用历史记录不可用。")
    except (QualityRuntimeError, ValueError) as exc:
        raise ApiError("PREVIEW_UNAVAILABLE", "生成应用历史记录暂时不可用。", 503) from exc
    return RuntimeHistoryResponse(items=[item for item in payload[:100] if isinstance(item, dict)])


@router.post("/previews/{preview_token}/runs", response_model=PreviewRunResponse)
def run_preview(
    preview_token: str,
    body: PreviewRunRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> PreviewRunResponse:
    preview = _active_preview(db, preview_token, user.id, request.app.state.preview_manager)
    runtime = db.scalar(select(PreviewRuntime).where(PreviewRuntime.preview_id == preview.id))
    credential = None
    if body.cost_authorization_id:
        if body.credential_id:
            credential = owned_credential(
                db,
                credential_id=body.credential_id,
                owner_id=user.id,
                project_id=preview.project_id,
            )
            if credential.scope not in {"runtime", "both"}:
                raise ApiError("CREDENTIAL_SCOPE_DENIED", "这个模型 Key 未授权用于产品运行。", 403)
            if credential.status != "verified":
                raise ApiError("CREDENTIAL_NOT_VERIFIED", "请先验证模型 Key。", 409)
        consume_authorization(
            db,
            authorization_id=body.cost_authorization_id,
            owner_id=user.id,
            project_id=preview.project_id,
            operation="preview_run",
            credential_id=credential.id if credential else None,
        )
        if credential:
            provider, credential = provider_for_credential(
                db,
                settings=request.app.state.settings,
                vault=request.app.state.secret_vault,
                owner_id=user.id,
                credential_id=credential.id,
                project_id=preview.project_id,
            )
        else:
            provider = request.app.state.provider
        result = generate_with_retry(
            provider,
            user_input=body.input,
            config=PreviewConfig.model_validate(preview.config_json),
            max_attempts=request.app.state.settings.ai_max_attempts,
        )
        run = PreviewRun(
            preview_id=preview.id,
            input_text=body.input,
            output_json=result.result.model_dump(mode="json"),
            provider=result.provider,
            model=result.model,
            usage_json=result.usage,
            latency_ms=result.latency_ms,
        )
        record_usage(
            db,
            settings=request.app.state.settings,
            owner_id=user.id,
            project_id=preview.project_id,
            task_id=None,
            credential=credential,
            operation="preview_run",
            provider=result.provider,
            model=result.model,
            usage=result.usage,
            trace_id=trace_id(request),
        )
    elif runtime and runtime.status == "ready" and runtime.base_url:
        started_at = datetime.now(UTC)
        try:
            response = request.app.state.preview_manager.request(
                process_ref=runtime.process_ref,
                base_url=runtime.base_url,
                method="POST",
                path="/api/v1/analyze",
                json_body={"input": body.input},
            )
            if response.status_code != 200:
                raise QualityRuntimeError("GENERATED_APP_ERROR", "生成应用没有接受本次输入。")
            generated_result = AgentResult.model_validate(response.json())
        except (QualityRuntimeError, ValueError) as exc:
            raise ApiError(
                getattr(exc, "code", "GENERATED_APP_INVALID_OUTPUT"),
                "生成应用本次运行失败，请稍后重试。",
                502,
            ) from exc
        latency_ms = (datetime.now(UTC) - started_at).total_seconds() * 1000
        run = PreviewRun(
            preview_id=preview.id,
            input_text=body.input,
            output_json=generated_result.model_dump(mode="json"),
            provider="generated_app",
            model="runtime-provider",
            usage_json={
                "provider_verification": "mock",
                "estimated": True,
                "source": "generated_runtime",
            },
            latency_ms=latency_ms,
        )
    else:
        result = generate_with_retry(
            request.app.state.provider,
            user_input=body.input,
            config=PreviewConfig.model_validate(preview.config_json),
            max_attempts=request.app.state.settings.ai_max_attempts,
        )
        run = PreviewRun(
            preview_id=preview.id,
            input_text=body.input,
            output_json=result.result.model_dump(mode="json"),
            provider=result.provider,
            model=result.model,
            usage_json=result.usage,
            latency_ms=result.latency_ms,
        )
    if credential is None:
        record_usage(
            db,
            settings=request.app.state.settings,
            owner_id=user.id,
            project_id=preview.project_id,
            task_id=None,
            credential=None,
            operation="preview_run",
            provider=run.provider,
            model=run.model,
            usage=run.usage_json,
            trace_id=trace_id(request),
        )
    db.add(run)
    db.flush()
    record_audit(
        db,
        project_id=preview.project_id,
        actor_id=user.id,
        action="preview_run",
        target_type="preview_run",
        target_id=run.id,
        result="success",
        trace_id=trace_id(request),
    )
    db.commit()
    return preview_run_response(run)


@router.post("/projects/{project_id}/preview-feedback", response_model=FeedbackResponse)
def preview_feedback(
    project_id: str,
    body: PreviewFeedbackRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> FeedbackResponse:
    project = owned_project(db, project_id, user.id, lock=True)
    preview = db.scalar(
        select(Preview)
        .where(Preview.project_id == project.id)
        .order_by(Preview.created_at.desc())
        .limit(1)
    )
    if not preview or preview.status != "ready":
        raise ApiError("PREVIEW_NOT_READY", "当前没有可验收的预览。", 409)
    preview_expires_at = preview.expires_at
    if preview_expires_at.tzinfo is None:
        preview_expires_at = preview_expires_at.replace(tzinfo=UTC)
    if preview_expires_at <= datetime.now(UTC):
        preview.status = "expired"
        runtime = db.scalar(select(PreviewRuntime).where(PreviewRuntime.preview_id == preview.id))
        if runtime:
            runtime.status = "expired"
            runtime.stopped_at = datetime.now(UTC)
            request.app.state.preview_manager.stop(runtime.process_ref)
        db.commit()
        raise ApiError("PREVIEW_EXPIRED", "这个预览已过期，不能继续提交验收反馈。", 410)
    classification, reason, solution, change_request = apply_feedback(db, project, body.feedback)
    db.flush()
    record_audit(
        db,
        project_id=project.id,
        actor_id=user.id,
        action="preview_feedback_classified",
        target_type="project",
        target_id=project.id,
        result=classification,
        trace_id=trace_id(request),
    )
    db.commit()
    return FeedbackResponse(
        classification=classification,
        reason=reason,
        next_stage=project.stage,
        project=project_detail(db, project),
        solution_artifact=artifact_response(solution) if solution else None,
        change_request_artifact=(artifact_response(change_request) if change_request else None),
    )


@router.get(
    "/projects/{project_id}/deployment-authorizations",
    response_model=DeploymentAuthorizationListResponse,
)
def list_deployment_authorizations(
    project_id: str,
    db: Db,
    user: CurrentUser,
) -> DeploymentAuthorizationListResponse:
    owned_project(db, project_id, user.id)
    items = list(
        db.scalars(
            select(DeploymentAuthorization)
            .where(
                DeploymentAuthorization.project_id == project_id,
                DeploymentAuthorization.actor_id == user.id,
            )
            .order_by(DeploymentAuthorization.created_at.desc())
        )
    )
    return DeploymentAuthorizationListResponse(
        items=[authorization_response(item) for item in items]
    )


@router.post(
    "/projects/{project_id}/deployment-authorizations",
    response_model=DeploymentAuthorizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def quote_deployment(
    project_id: str,
    body: DeploymentAuthorizationRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> DeploymentAuthorizationResponse:
    project = owned_project(db, project_id, user.id)
    acceptance = db.scalar(
        select(PreviewAcceptance)
        .where(PreviewAcceptance.project_id == project.id)
        .order_by(PreviewAcceptance.created_at.desc())
        .limit(1)
    )
    if not acceptance:
        raise ApiError("PREVIEW_ACCEPTANCE_REQUIRED", "请先完成预览验收。", 409)
    credential = owned_credential(
        db,
        credential_id=body.credential_id,
        owner_id=user.id,
        project_id=project.id,
    )
    if credential.provider != "volcano_engine" or credential.scope != "deployment":
        raise not_found("云凭证")
    settings: Settings = request.app.state.settings
    if settings.deployment_mode == "external" and credential.status != "verified":
        raise ApiError("CLOUD_CREDENTIAL_NOT_VERIFIED", "请先通过受信任适配器验证云凭证。", 409)
    if body.target_deployment_id:
        owned_deployment(db, deployment_id=body.target_deployment_id, owner_id=user.id)
    item = create_deployment_authorization(
        db,
        settings=settings,
        adapter=request.app.state.deployment_adapter,
        project=project,
        actor_id=user.id,
        credential=credential,
        action=body.action,
        target_deployment_id=body.target_deployment_id,
        region=body.region,
    )
    record_audit(
        db,
        project_id=project.id,
        actor_id=user.id,
        action="deployment_authorization_created",
        target_type="deployment_authorization",
        target_id=item.id,
        result="pending_confirmation",
        trace_id=trace_id(request),
    )
    db.commit()
    return authorization_response(item)


@router.post(
    "/deployment-authorizations/{authorization_id}/confirm",
    response_model=DeploymentAuthorizationResponse,
)
def confirm_deployment_authorization(
    authorization_id: str,
    body: CredentialRevokeRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> DeploymentAuthorizationResponse:
    if not body.confirm:
        raise ApiError("DEPLOYMENT_CONFIRMATION_REQUIRED", "请明确确认部署费用和权限。", 409)
    item = owned_deployment_authorization(db, authorization_id=authorization_id, owner_id=user.id)
    if item.status == "expired":
        db.commit()
        raise ApiError("DEPLOYMENT_AUTHORIZATION_EXPIRED", "部署授权已过期，请重新确认。", 409)
    if item.status == "pending":
        item.status = "confirmed"
        item.confirmed_at = datetime.now(UTC)
        record_audit(
            db,
            project_id=item.project_id,
            actor_id=user.id,
            action="deployment_authorization_confirmed",
            target_type="deployment_authorization",
            target_id=item.id,
            result="success",
            trace_id=trace_id(request),
        )
        db.commit()
    return authorization_response(item)


@router.post(
    "/projects/{project_id}/deployments",
    response_model=DeploymentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_deployment(
    project_id: str,
    body: DeploymentStartRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> DeploymentResponse:
    project = owned_project(db, project_id, user.id, lock=True)
    authorization = owned_deployment_authorization(
        db, authorization_id=body.authorization_id, owner_id=user.id
    )
    if authorization.project_id != project.id or authorization.action != "deploy":
        raise ApiError("DEPLOYMENT_AUTHORIZATION_MISMATCH", "部署授权与本项目不匹配。", 409)
    item, created = start_deployment_record(
        db,
        project=project,
        authorization=authorization,
        trace_id=trace_id(request),
    )
    if created:
        record_audit(
            db,
            project_id=project.id,
            actor_id=user.id,
            action="deployment_started",
            target_type="deployment",
            target_id=item.id,
            result="accepted",
            trace_id=trace_id(request),
        )
    db.commit()
    response = deployment_response(db, item)
    if created:
        request.app.state.deployment_runner.enqueue(item.id)
    return response


@router.get(
    "/projects/{project_id}/deployments",
    response_model=DeploymentListResponse,
)
def list_deployments(
    project_id: str,
    db: Db,
    user: CurrentUser,
) -> DeploymentListResponse:
    owned_project(db, project_id, user.id)
    items = list(
        db.scalars(
            select(Deployment)
            .where(Deployment.project_id == project_id)
            .order_by(Deployment.revision.desc())
        )
    )
    return DeploymentListResponse(items=[deployment_response(db, item) for item in items])


@router.get("/deployments/{deployment_id}", response_model=DeploymentResponse)
def get_deployment(
    deployment_id: str,
    db: Db,
    user: CurrentUser,
) -> DeploymentResponse:
    return deployment_response(
        db, owned_deployment(db, deployment_id=deployment_id, owner_id=user.id)
    )


@router.post(
    "/deployments/{deployment_id}/rollback",
    response_model=DeploymentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def rollback_deployment(
    deployment_id: str,
    body: DeploymentRollbackRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> DeploymentResponse:
    if not body.confirm:
        raise ApiError("ROLLBACK_CONFIRMATION_REQUIRED", "回滚前需要明确确认。", 409)
    target = owned_deployment(db, deployment_id=deployment_id, owner_id=user.id)
    project = owned_project(db, target.project_id, user.id, lock=True)
    authorization = owned_deployment_authorization(
        db, authorization_id=body.authorization_id, owner_id=user.id
    )
    if (
        authorization.project_id != project.id
        or authorization.action != "rollback"
        or authorization.target_deployment_id != target.id
    ):
        raise ApiError("ROLLBACK_AUTHORIZATION_MISMATCH", "回滚授权与目标版本不匹配。", 409)
    item, created = start_deployment_record(
        db,
        project=project,
        authorization=authorization,
        trace_id=trace_id(request),
    )
    db.commit()
    response = deployment_response(db, item)
    if created:
        request.app.state.deployment_runner.enqueue(item.id)
    return response


@router.post(
    "/projects/{project_id}/delivery-packages",
    response_model=DeliveryPackageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project_delivery(
    project_id: str,
    body: DeliveryPackageCreateRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> DeliveryPackageResponse:
    if not body.confirm:
        raise ApiError("DELIVERY_CONFIRMATION_REQUIRED", "生成交付包前需要明确确认。", 409)
    project = owned_project(db, project_id, user.id, lock=True)
    deployment = owned_deployment(db, deployment_id=body.deployment_id, owner_id=user.id)
    if deployment.project_id != project.id:
        raise ApiError("DELIVERY_DEPLOYMENT_MISMATCH", "交付版本与本项目不匹配。", 409)
    item, created = create_delivery_package(
        db,
        settings=request.app.state.settings,
        project=project,
        deployment=deployment,
    )
    if created:
        record_audit(
            db,
            project_id=project.id,
            actor_id=user.id,
            action="delivery_package_created",
            target_type="delivery_package",
            target_id=item.id,
            result="success",
            trace_id=trace_id(request),
        )
    db.commit()
    return delivery_response(item)


@router.get(
    "/projects/{project_id}/delivery-packages",
    response_model=DeliveryPackageListResponse,
)
def list_delivery_packages(
    project_id: str,
    db: Db,
    user: CurrentUser,
) -> DeliveryPackageListResponse:
    owned_project(db, project_id, user.id)
    items = list(
        db.scalars(
            select(DeliveryPackage)
            .where(DeliveryPackage.project_id == project_id)
            .order_by(DeliveryPackage.revision.desc())
        )
    )
    return DeliveryPackageListResponse(items=[delivery_response(item) for item in items])


@router.get("/delivery-packages/{package_id}", response_model=DeliveryPackageResponse)
def get_delivery_package(
    package_id: str,
    db: Db,
    user: CurrentUser,
) -> DeliveryPackageResponse:
    return delivery_response(owned_delivery(db, package_id, user.id))


@router.get("/delivery-packages/{package_id}/download")
def download_delivery_package(
    package_id: str,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> FileResponse:
    item = owned_delivery(db, package_id, user.id)
    return FileResponse(
        path=package_path(request.app.state.settings, item),
        media_type="application/zip",
        filename=item.filename,
    )


@router.post(
    "/delivery-packages/{package_id}/github-sync",
    response_model=GithubSyncResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def sync_package_to_github(
    package_id: str,
    body: GithubSyncRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> GithubSyncResponse:
    if not body.confirm:
        raise ApiError("GITHUB_SYNC_CONFIRMATION_REQUIRED", "GitHub 同步前需要明确确认。", 409)
    package = owned_delivery(db, package_id, user.id)
    item = sync_delivery_to_github(
        db,
        settings=request.app.state.settings,
        owner_id=user.id,
        package=package,
        repository=body.repository_full_name,
        branch=body.branch,
    )
    record_audit(
        db,
        project_id=package.project_id,
        actor_id=user.id,
        action="github_sync_requested",
        target_type="github_sync",
        target_id=item.id,
        result=item.status,
        trace_id=trace_id(request),
    )
    db.commit()
    return github_sync_response(item)


@router.get("/github-syncs/{sync_id}", response_model=GithubSyncResponse)
def get_github_sync(
    sync_id: str,
    db: Db,
    user: CurrentUser,
) -> GithubSyncResponse:
    item = db.scalar(
        select(GithubSync).where(GithubSync.id == sync_id, GithubSync.owner_id == user.id)
    )
    if not item:
        raise not_found("GitHub 同步记录")
    return github_sync_response(item)


def _owned_product_graph(db: Db, graph_id: str, user_id: str) -> ProductGraph:
    graph = db.scalar(
        select(ProductGraph)
        .join(Project, Project.id == ProductGraph.project_id)
        .where(
            ProductGraph.id == graph_id,
            Project.owner_id == user_id,
            Project.status != ProjectStatus.DELETED.value,
        )
    )
    if not graph:
        raise not_found("产品流程图")
    return graph


@router.post(
    "/projects/{project_id}/product-graph/initialize",
    response_model=ProductGraphResponse,
)
def initialize_product_graph_route(
    project_id: str,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> ProductGraphResponse:
    project = owned_project(db, project_id, user.id, lock=True)
    try:
        graph, created = initialize_product_graph(db, project)
        if created:
            record_audit(
                db,
                project_id=project.id,
                actor_id=user.id,
                action="product_graph_initialized",
                target_type="product_graph",
                target_id=graph.id,
                result="success",
                trace_id=trace_id(request),
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        graph = active_graph(db, project_id)
        if not graph:
            raise ApiError("PRODUCT_GRAPH_CONFLICT", "产品流程图初始化冲突，请重试。", 409)
    return graph_response(db, graph)


@router.get(
    "/projects/{project_id}/product-graph",
    response_model=ProductGraphResponse,
)
def get_product_graph_route(
    project_id: str,
    db: Db,
    user: CurrentUser,
) -> ProductGraphResponse:
    owned_project(db, project_id, user.id)
    return graph_response(db, require_active_graph(db, project_id))


@router.get(
    "/projects/{project_id}/decision-center",
    response_model=DecisionCenterResponse,
)
def get_decision_center_route(
    project_id: str,
    db: Db,
    user: CurrentUser,
) -> DecisionCenterResponse:
    owned_project(db, project_id, user.id)
    return decision_center_response(db, require_active_graph(db, project_id))


@router.post(
    "/decisions/{decision_id}/confirm",
    response_model=ProductDecisionActionResponse,
)
def confirm_product_decision_route(
    decision_id: str,
    body: ConfirmProductDecisionRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> ProductDecisionActionResponse:
    decision = owned_decision(db, decision_id, user.id)
    owned_project(db, decision.project_id, user.id, lock=True)
    try:
        decision, change = confirm_product_decision(
            db,
            decision=decision,
            option_key=body.option_key,
            idempotency_key=body.idempotency_key,
        )
        record_audit(
            db,
            project_id=decision.project_id,
            actor_id=user.id,
            action="product_decision_confirmed",
            target_type="product_decision",
            target_id=decision.id,
            result=body.option_key,
            trace_id=trace_id(request),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(
            "DECISION_CONFIRM_CONFLICT", "产品决策确认发生冲突，请刷新后重试。", 409
        ) from None
    graph = require_active_graph(db, decision.project_id)
    return ProductDecisionActionResponse(
        decision=decision_response(db, decision),
        change_request=change_request_response(change),
        next_action=dashboard_next_action(db, graph),
    )


@router.post(
    "/product-graphs/{graph_id}/simulations",
    response_model=SimulationRunResponse,
)
def start_product_simulation_route(
    graph_id: str,
    body: SimulationStartRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> SimulationRunResponse:
    graph = _owned_product_graph(db, graph_id, user.id)
    owned_project(db, graph.project_id, user.id, lock=True)
    try:
        run, created = start_simulation(
            db,
            graph=graph,
            persona_key=body.persona_key,
            idempotency_key=body.idempotency_key,
        )
        if created:
            record_audit(
                db,
                project_id=graph.project_id,
                actor_id=user.id,
                action="user_simulation_started",
                target_type="simulation_run",
                target_id=run.id,
                result="accepted",
                trace_id=trace_id(request),
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError("SIMULATION_START_CONFLICT", "虚拟用户走查启动冲突，请重试。", 409) from None
    return simulation_response(db, run)


@router.get("/simulations/{run_id}", response_model=SimulationRunResponse)
def get_product_simulation_route(
    run_id: str,
    db: Db,
    user: CurrentUser,
) -> SimulationRunResponse:
    return simulation_response(db, owned_simulation(db, run_id, user.id))


@router.post("/simulations/{run_id}/advance", response_model=SimulationRunResponse)
def advance_product_simulation_route(
    run_id: str,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> SimulationRunResponse:
    run = owned_simulation(db, run_id, user.id)
    owned_project(db, run.project_id, user.id, lock=True)
    run = advance_simulation(db, run)
    record_audit(
        db,
        project_id=run.project_id,
        actor_id=user.id,
        action="user_simulation_advanced",
        target_type="simulation_run",
        target_id=run.id,
        result=run.status,
        trace_id=trace_id(request),
    )
    db.commit()
    return simulation_response(db, run)


@router.post(
    "/findings/{finding_id}/resolve",
    response_model=FindingResolutionResponse,
)
def resolve_product_finding_route(
    finding_id: str,
    body: ResolveFindingRequest,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> FindingResolutionResponse:
    finding = owned_finding(db, finding_id, user.id)
    run = owned_simulation(db, finding.run_id, user.id)
    owned_project(db, run.project_id, user.id, lock=True)
    try:
        finding, run, change = resolve_finding(
            db,
            finding=finding,
            resolution_key=body.resolution_key,
            idempotency_key=body.idempotency_key,
        )
        record_audit(
            db,
            project_id=run.project_id,
            actor_id=user.id,
            action="simulation_finding_resolved",
            target_type="friction_finding",
            target_id=finding.id,
            result=body.resolution_key,
            trace_id=trace_id(request),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(
            "FINDING_RESOLUTION_CONFLICT", "问题处理发生冲突，请刷新后重试。", 409
        ) from None
    return FindingResolutionResponse(
        finding=finding_response(db, finding),
        simulation=simulation_response(db, run),
        change_request=change_request_response(change),
    )


@router.get(
    "/projects/{project_id}/product-dashboard",
    response_model=ProductDashboardResponse,
)
def get_product_dashboard_route(
    project_id: str,
    db: Db,
    user: CurrentUser,
) -> ProductDashboardResponse:
    owned_project(db, project_id, user.id)
    return dashboard_response(db, require_active_graph(db, project_id))
