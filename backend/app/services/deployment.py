from __future__ import annotations

import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import ApiError, not_found
from app.models import (
    CodeVersion,
    CredentialRef,
    Deployment,
    DeploymentAuthorization,
    DeploymentEvent,
    Preview,
    PreviewAcceptance,
    Project,
)
from app.models.enums import ProjectStage
from app.schemas.contracts import (
    DeploymentAuthorizationResponse,
    DeploymentEventResponse,
    DeploymentResponse,
    PreviewAcceptanceResponse,
)
from app.services.credentials import SecretVault
from app.services.workflow import transition


@dataclass(frozen=True, slots=True)
class DeploymentResult:
    status: str
    provider_ref: str
    deployment_url: str | None
    evidence: dict[str, Any]


class DeploymentAdapter(Protocol):
    def estimate(self, *, region: str, action: str) -> dict[str, Any]: ...

    def deploy(
        self,
        *,
        credentials: dict[str, str],
        project: Project,
        code_version: CodeVersion,
        region: str,
    ) -> DeploymentResult: ...

    def rollback(
        self,
        *,
        credentials: dict[str, str],
        target: Deployment,
        region: str,
    ) -> DeploymentResult: ...


class MockDeploymentAdapter:
    def estimate(self, *, region: str, action: str) -> dict[str, Any]:
        return {
            "pricing_configured": False,
            "currency": "CNY",
            "amount_minor": None,
            "region": region,
            "action": action,
            "note": "演练模式不创建云资源；真实费用必须由部署适配器返回。",
        }

    def deploy(
        self,
        *,
        credentials: dict[str, str],
        project: Project,
        code_version: CodeVersion,
        region: str,
    ) -> DeploymentResult:
        return DeploymentResult(
            status="simulated",
            provider_ref=f"mock-deploy-{uuid4()}",
            deployment_url=None,
            evidence={
                "mode": "mock",
                "created_cloud_resources": False,
                "region": region,
                "commit_ref": code_version.commit_ref,
            },
        )

    def rollback(
        self,
        *,
        credentials: dict[str, str],
        target: Deployment,
        region: str,
    ) -> DeploymentResult:
        return DeploymentResult(
            status="simulated",
            provider_ref=f"mock-rollback-{uuid4()}",
            deployment_url=None,
            evidence={
                "mode": "mock",
                "created_cloud_resources": False,
                "region": region,
                "rollback_target": target.provider_ref,
            },
        )


class ExternalDeploymentAdapter:
    """Trusted adapter boundary; provider-specific API details stay outside this app."""

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.deployment_adapter_base_url.rstrip("/")
        self.token = settings.deployment_adapter_token.get_secret_value()
        self.timeout = settings.deployment_timeout_seconds

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}{path}",
                    headers={"Authorization": f"Bearer {self.token}"},
                    json=payload,
                )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise TypeError("adapter response must be an object")
            return body
        except httpx.TimeoutException as exc:
            raise ApiError("DEPLOYMENT_TIMEOUT", "部署服务响应超时。", 504) from exc
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise ApiError("DEPLOYMENT_ADAPTER_UNAVAILABLE", "部署服务暂时不可用。", 502) from exc

    def estimate(self, *, region: str, action: str) -> dict[str, Any]:
        result = self._post("/v1/estimates", {"provider": "volcano_engine", "region": region, "action": action})
        return {
            "pricing_configured": bool(result.get("pricing_configured")),
            "currency": str(result.get("currency") or "CNY"),
            "amount_minor": result.get("amount_minor"),
            "region": region,
            "action": action,
            "note": str(result.get("note") or "由受信任部署适配器返回。")[:300],
        }

    def _result(self, body: dict[str, Any]) -> DeploymentResult:
        status = str(body.get("status") or "")
        provider_ref = str(body.get("provider_ref") or "")
        deployment_url = body.get("deployment_url")
        if status != "succeeded" or not provider_ref or not isinstance(deployment_url, str):
            raise ApiError("DEPLOYMENT_INVALID_RESULT", "部署服务返回结果不完整。", 502)
        parsed = urlparse(deployment_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ApiError("DEPLOYMENT_HTTPS_REQUIRED", "部署结果没有有效 HTTPS 地址。", 502)
        evidence = body.get("evidence") if isinstance(body.get("evidence"), dict) else {}
        return DeploymentResult(status, provider_ref, deployment_url, evidence)

    def deploy(
        self,
        *,
        credentials: dict[str, str],
        project: Project,
        code_version: CodeVersion,
        region: str,
    ) -> DeploymentResult:
        return self._result(
            self._post(
                "/v1/deployments",
                {
                    "provider": "volcano_engine",
                    "region": region,
                    "environment": "production",
                    "project_id": project.id,
                    "commit_ref": code_version.commit_ref,
                    "credentials": credentials,
                },
            )
        )

    def rollback(
        self,
        *,
        credentials: dict[str, str],
        target: Deployment,
        region: str,
    ) -> DeploymentResult:
        if not target.provider_ref:
            raise ApiError("ROLLBACK_TARGET_INVALID", "目标部署没有可回滚的云版本。", 409)
        return self._result(
            self._post(
                "/v1/rollbacks",
                {
                    "provider": "volcano_engine",
                    "region": region,
                    "target_provider_ref": target.provider_ref,
                    "credentials": credentials,
                },
            )
        )


def build_deployment_adapter(settings: Settings) -> DeploymentAdapter:
    if settings.deployment_mode == "mock":
        return MockDeploymentAdapter()
    return ExternalDeploymentAdapter(settings)


def acceptance_response(item: PreviewAcceptance) -> PreviewAcceptanceResponse:
    return PreviewAcceptanceResponse(
        id=item.id,
        project_id=item.project_id,
        preview_id=item.preview_id,
        code_version_id=item.code_version_id,
        decision=item.decision,
        checklist={key: bool(value) for key, value in item.checklist_json.items()},
        created_at=item.created_at,
    )


def authorization_response(item: DeploymentAuthorization) -> DeploymentAuthorizationResponse:
    return DeploymentAuthorizationResponse(
        id=item.id,
        project_id=item.project_id,
        credential_ref_id=item.credential_ref_id,
        action=item.action,
        target_deployment_id=item.target_deployment_id,
        provider=item.provider,
        region=item.region,
        environment=item.environment,
        permission_scope=item.permission_scope_json,
        estimated_cost=item.estimated_cost_json,
        status=item.status,
        expires_at=item.expires_at,
        confirmed_at=item.confirmed_at,
        consumed_at=item.consumed_at,
        created_at=item.created_at,
    )


def deployment_response(db: Session, item: Deployment) -> DeploymentResponse:
    events = list(
        db.scalars(
            select(DeploymentEvent)
            .where(DeploymentEvent.deployment_id == item.id)
            .order_by(DeploymentEvent.sequence)
        )
    )
    return DeploymentResponse(
        id=item.id,
        project_id=item.project_id,
        preview_id=item.preview_id,
        code_version_id=item.code_version_id,
        authorization_id=item.authorization_id,
        previous_deployment_id=item.previous_deployment_id,
        revision=item.revision,
        kind=item.kind,
        provider=item.provider,
        region=item.region,
        environment=item.environment,
        status=item.status,
        provider_ref=item.provider_ref,
        deployment_url=item.deployment_url,
        checkpoint=item.checkpoint_json,
        evidence=item.evidence_json,
        attempts=item.attempts,
        error_code=item.error_code,
        trace_id=item.trace_id,
        deployed_at=item.deployed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        events=[
            DeploymentEventResponse(
                sequence=event.sequence,
                type=event.type,
                message=event.message,
                payload=event.payload_json,
                created_at=event.created_at,
            )
            for event in events
        ],
    )


def _event(db: Session, deployment: Deployment, event_type: str, message: str, payload: dict[str, Any]) -> None:
    sequence = int(
        db.scalar(
            select(func.max(DeploymentEvent.sequence)).where(
                DeploymentEvent.deployment_id == deployment.id
            )
        )
        or 0
    ) + 1
    db.add(
        DeploymentEvent(
            deployment_id=deployment.id,
            sequence=sequence,
            type=event_type,
            message=message,
            payload_json=payload,
        )
    )


def owned_deployment(db: Session, *, deployment_id: str, owner_id: str) -> Deployment:
    item = db.scalar(
        select(Deployment)
        .join(Project, Project.id == Deployment.project_id)
        .where(Deployment.id == deployment_id, Project.owner_id == owner_id)
    )
    if not item:
        raise not_found("部署记录")
    return item


def owned_deployment_authorization(
    db: Session, *, authorization_id: str, owner_id: str
) -> DeploymentAuthorization:
    item = db.scalar(
        select(DeploymentAuthorization)
        .join(Project, Project.id == DeploymentAuthorization.project_id)
        .where(DeploymentAuthorization.id == authorization_id, Project.owner_id == owner_id)
    )
    if not item:
        raise not_found("部署授权")
    expires = item.expires_at if item.expires_at.tzinfo else item.expires_at.replace(tzinfo=UTC)
    if expires <= datetime.now(UTC) and item.status in {"pending", "confirmed"}:
        item.status = "expired"
        db.flush()
    return item


def create_deployment_authorization(
    db: Session,
    *,
    settings: Settings,
    adapter: DeploymentAdapter,
    project: Project,
    actor_id: str,
    credential: CredentialRef,
    action: str,
    target_deployment_id: str | None,
    region: str,
) -> DeploymentAuthorization:
    if not settings.deployment_enabled:
        raise ApiError("DEPLOYMENT_DISABLED", "正式部署能力当前未启用。", 409)
    estimated_cost = adapter.estimate(region=region, action=action)
    item = DeploymentAuthorization(
        project_id=project.id,
        actor_id=actor_id,
        credential_ref_id=credential.id,
        action=action,
        target_deployment_id=target_deployment_id,
        provider="volcano_engine",
        region=region,
        environment="production",
        permission_scope_json={
            "services": ["vefaas"],
            "actions": [action],
            "project_id": project.id,
            "region": region,
        },
        estimated_cost_json=estimated_cost,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    db.add(item)
    db.flush()
    return item


def start_deployment_record(
    db: Session,
    *,
    project: Project,
    authorization: DeploymentAuthorization,
    trace_id: str,
) -> tuple[Deployment, bool]:
    existing = db.scalar(
        select(Deployment).where(Deployment.authorization_id == authorization.id)
    )
    if existing:
        return existing, False
    if authorization.status != "confirmed":
        raise ApiError("DEPLOYMENT_AUTHORIZATION_REQUIRED", "请先确认部署费用和权限。", 409)
    acceptance = db.scalar(
        select(PreviewAcceptance)
        .where(PreviewAcceptance.project_id == project.id)
        .order_by(PreviewAcceptance.created_at.desc())
        .limit(1)
    )
    if not acceptance:
        raise ApiError("PREVIEW_ACCEPTANCE_REQUIRED", "请先完成预览验收。", 409)
    preview = db.get(Preview, acceptance.preview_id)
    code_version = db.get(CodeVersion, acceptance.code_version_id)
    if not preview or not code_version or code_version.test_status != "quality_passed":
        raise ApiError("DEPLOYMENT_VERSION_INVALID", "验收版本没有通过质量门。", 409)
    revision = int(
        db.scalar(select(func.max(Deployment.revision)).where(Deployment.project_id == project.id))
        or 0
    ) + 1
    target = None
    kind = authorization.action
    if kind == "rollback":
        target = db.get(Deployment, authorization.target_deployment_id)
        if not target or target.project_id != project.id or target.status not in {"succeeded", "simulated"}:
            raise ApiError("ROLLBACK_TARGET_INVALID", "回滚目标不可用。", 409)
    item = Deployment(
        project_id=project.id,
        preview_id=preview.id,
        code_version_id=code_version.id,
        credential_ref_id=authorization.credential_ref_id,
        authorization_id=authorization.id,
        previous_deployment_id=target.id if target else None,
        revision=revision,
        kind=kind,
        provider=authorization.provider,
        region=authorization.region,
        environment=authorization.environment,
        status="queued",
        checkpoint_json={"last_completed_step": "accepted"},
        trace_id=trace_id,
    )
    authorization.status = "consumed"
    authorization.consumed_at = datetime.now(UTC)
    if project.stage == ProjectStage.PREVIEW_REVIEW.value:
        transition(project, ProjectStage.DEPLOYMENT.value)
    db.add(item)
    db.flush()
    _event(db, item, "progress", "部署任务已受理。", {"checkpoint": "accepted"})
    return item, True


class PersistentDeploymentRunner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        vault: SecretVault,
        adapter: DeploymentAdapter,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.vault = vault
        self.adapter = adapter
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="deployment-task")
        self._lock = threading.Lock()
        self._scheduled: set[str] = set()

    def recover(self) -> None:
        with self.session_factory() as db:
            items = list(db.scalars(select(Deployment).where(Deployment.status.in_(["queued", "running"]))))
            for item in items:
                if item.status == "running":
                    item.status = "queued"
                    _event(db, item, "retry", "服务恢复后重新执行部署。", item.checkpoint_json)
            ids = [item.id for item in items]
            db.commit()
        for deployment_id in ids:
            self.enqueue(deployment_id)

    def enqueue(self, deployment_id: str) -> None:
        with self._lock:
            if deployment_id in self._scheduled:
                return
            self._scheduled.add(deployment_id)
        future = self.executor.submit(self._run, deployment_id)
        future.add_done_callback(lambda done, value=deployment_id: self._finish(value, done))

    def _finish(self, deployment_id: str, future: Future[None]) -> None:
        with self._lock:
            self._scheduled.discard(deployment_id)
        future.exception()

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)

    def _run(self, deployment_id: str) -> None:
        try:
            with self.session_factory() as db:
                item = db.get(Deployment, deployment_id)
                if not item or item.status in {"succeeded", "simulated", "failed"}:
                    return
                project = db.get(Project, item.project_id)
                code_version = db.get(CodeVersion, item.code_version_id)
                credential = db.get(CredentialRef, item.credential_ref_id)
                target = db.get(Deployment, item.previous_deployment_id) if item.previous_deployment_id else None
                if not project or not code_version or not credential:
                    raise ApiError("DEPLOYMENT_CONTEXT_MISSING", "部署上下文不完整。", 409)
                item.status = "running"
                item.attempts += 1
                item.checkpoint_json = {"last_completed_step": "credentials_loaded"}
                _event(db, item, "progress", "已加载受控部署上下文。", item.checkpoint_json)
                owner_id = project.owner_id
                secret_ref = credential.secret_ref
                action = item.kind
                region = item.region
                db.commit()

            raw = self.vault.load(owner_id=owner_id, secret_ref=secret_ref)
            credentials = json.loads(raw)
            if not isinstance(credentials, dict) or not all(
                isinstance(credentials.get(key), str) and credentials[key]
                for key in ("access_key_id", "secret_access_key")
            ):
                raise ApiError("CLOUD_CREDENTIAL_INVALID", "云账号凭证不可用。", 409)
            if action == "rollback":
                if not target:
                    raise ApiError("ROLLBACK_TARGET_INVALID", "回滚目标不可用。", 409)
                result = self.adapter.rollback(credentials=credentials, target=target, region=region)
            else:
                result = self.adapter.deploy(
                    credentials=credentials,
                    project=project,
                    code_version=code_version,
                    region=region,
                )
            with self.session_factory() as db:
                item = db.get(Deployment, deployment_id)
                if not item:
                    return
                item.status = result.status
                item.provider_ref = result.provider_ref
                item.deployment_url = result.deployment_url
                item.evidence_json = result.evidence
                item.checkpoint_json = {"last_completed_step": "deployment_verified"}
                item.deployed_at = datetime.now(UTC)
                _event(
                    db,
                    item,
                    "done",
                    "部署演练完成，未创建云资源。"
                    if result.status == "simulated"
                    else "正式部署与 HTTPS 地址验证完成。",
                    {
                        "status": result.status,
                        "https_verified": bool(result.deployment_url),
                        "checkpoint": "deployment_verified",
                    },
                )
                db.commit()
        except Exception as exc:  # noqa: BLE001
            with self.session_factory() as db:
                item = db.get(Deployment, deployment_id)
                if item:
                    item.status = "failed"
                    item.error_code = getattr(exc, "code", "DEPLOYMENT_FAILED")
                    item.checkpoint_json = {
                        **item.checkpoint_json,
                        "last_completed_step": "deployment_failed",
                    }
                    _event(
                        db,
                        item,
                        "error",
                        "部署未完成，已保留上一可用版本。",
                        {"error_code": item.error_code},
                    )
                    db.commit()
