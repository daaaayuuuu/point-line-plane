from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError, not_found
from app.models import CostAuthorization, CredentialRef, Project, QuotaAccount, UsageLedger
from app.services.providers import AIProvider, build_user_provider

OPERATION_BUDGETS: dict[str, tuple[int, int]] = {
    "requirements_prd": (6_000, 2_500),
    "solution": (5_000, 2_000),
    "development": (12_000, 8_000),
    "repair": (8_000, 5_000),
    "preview_run": (2_000, 1_500),
    "credential_verify": (200, 100),
}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SecretVault:
    """Local encrypted secret carrier; database rows contain only opaque references."""

    def __init__(self, settings: Settings) -> None:
        configured = settings.credential_key_bytes
        if configured is None:
            configured = hashlib.sha256(
                (
                    "product-factory-local-credential-v1:"
                    + settings.session_secret.get_secret_value()
                ).encode("utf-8")
            ).digest()
        self._key = configured
        self._root = settings.credential_store_root.resolve()

    def initialize(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self._root, 0o700)

    def _path(self, secret_ref: str) -> Path:
        prefix = "local-aesgcm:"
        if not secret_ref.startswith(prefix):
            raise ApiError("CREDENTIAL_REF_INVALID", "凭证引用无效。", 409)
        try:
            identifier = str(UUID(secret_ref.removeprefix(prefix)))
        except ValueError as exc:
            raise ApiError("CREDENTIAL_REF_INVALID", "凭证引用无效。", 409) from exc
        candidate = (self._root / f"{identifier}.secret").resolve()
        if candidate.parent != self._root:
            raise ApiError("CREDENTIAL_REF_INVALID", "凭证引用无效。", 409)
        return candidate

    def store(self, *, owner_id: str, secret: str) -> str:
        self.initialize()
        identifier = str(uuid4())
        secret_ref = f"local-aesgcm:{identifier}"
        nonce = os.urandom(12)
        associated_data = f"{owner_id}:{secret_ref}:v1".encode()
        ciphertext = AESGCM(self._key).encrypt(nonce, secret.encode("utf-8"), associated_data)
        payload = json.dumps(
            {
                "version": 1,
                "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
                "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
            },
            separators=(",", ":"),
        ).encode("utf-8")
        target = self._path(secret_ref)
        temporary = self._root / f".{identifier}.{uuid4()}.tmp"
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            os.chmod(target, 0o600)
        finally:
            if temporary.exists():
                temporary.unlink()
        return secret_ref

    def load(self, *, owner_id: str, secret_ref: str) -> str:
        target = self._path(secret_ref)
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            nonce = base64.urlsafe_b64decode(payload["nonce"])
            ciphertext = base64.urlsafe_b64decode(payload["ciphertext"])
            associated_data = f"{owner_id}:{secret_ref}:v1".encode()
            value = AESGCM(self._key).decrypt(nonce, ciphertext, associated_data)
            return value.decode("utf-8")
        except (OSError, KeyError, ValueError, TypeError, InvalidTag) as exc:
            raise ApiError("CREDENTIAL_UNAVAILABLE", "模型凭证当前不可用，请重新连接。", 409) from exc

    def delete(self, secret_ref: str) -> None:
        target = self._path(secret_ref)
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise ApiError("CREDENTIAL_DELETE_FAILED", "凭证撤销失败，请稍后重试。", 503) from exc

    def fingerprint(self, secret: str) -> str:
        return hmac.new(self._key, secret.encode("utf-8"), hashlib.sha256).hexdigest()


def masked_hint(secret: str) -> str:
    suffix = secret[-4:] if len(secret) >= 4 else "****"
    return f"••••••••{suffix}"


def ensure_quota_account(db: Session, *, user_id: str, settings: Settings) -> QuotaAccount:
    account = db.scalar(select(QuotaAccount).where(QuotaAccount.user_id == user_id))
    if account:
        return account
    account = QuotaAccount(user_id=user_id, granted_units=settings.free_quota_units)
    db.add(account)
    db.flush()
    return account


def remaining_quota(account: QuotaAccount) -> int:
    return max(account.granted_units - account.consumed_units - account.reserved_units, 0)


def owned_credential(
    db: Session,
    *,
    credential_id: str,
    owner_id: str,
    project_id: str | None = None,
    active_only: bool = True,
) -> CredentialRef:
    credential = db.scalar(
        select(CredentialRef).where(
            CredentialRef.id == credential_id,
            CredentialRef.owner_id == owner_id,
        )
    )
    if not credential:
        raise not_found("模型凭证")
    if project_id is not None and credential.project_id and credential.project_id != project_id:
        raise not_found("模型凭证")
    if credential.expires_at and _aware(credential.expires_at) <= datetime.now(UTC):
        credential.status = "expired"
        db.flush()
    if active_only and credential.status in {"revoked", "expired", "invalid"}:
        raise ApiError("CREDENTIAL_INACTIVE", "模型凭证已失效，请重新连接。", 409)
    return credential


def provider_for_credential(
    db: Session,
    *,
    settings: Settings,
    vault: SecretVault,
    owner_id: str,
    credential_id: str,
    project_id: str | None,
) -> tuple[AIProvider, CredentialRef]:
    credential = owned_credential(
        db,
        credential_id=credential_id,
        owner_id=owner_id,
        project_id=project_id,
    )
    secret = vault.load(owner_id=owner_id, secret_ref=credential.secret_ref)
    provider = build_user_provider(
        settings,
        provider=credential.provider,
        api_key=secret,
        model=credential.model,
        verified=credential.status == "verified",
    )
    credential.last_used_at = datetime.now(UTC)
    return provider, credential


def _estimate_cost(
    settings: Settings, *, input_tokens: int, output_tokens: int
) -> tuple[int, bool]:
    pricing_configured = bool(
        settings.ai_input_cost_microusd_per_million
        or settings.ai_output_cost_microusd_per_million
    )
    cost = (
        input_tokens * settings.ai_input_cost_microusd_per_million
        + output_tokens * settings.ai_output_cost_microusd_per_million
    ) // 1_000_000
    return int(cost), pricing_configured


def create_cost_authorization(
    db: Session,
    *,
    settings: Settings,
    owner_id: str,
    project: Project,
    operation: str,
    credential: CredentialRef | None,
) -> CostAuthorization:
    if operation not in OPERATION_BUDGETS:
        raise ApiError("UNSUPPORTED_COST_OPERATION", "这个操作暂不支持费用预估。", 422)
    input_tokens, output_tokens = OPERATION_BUDGETS[operation]
    account = ensure_quota_account(db, user_id=owner_id, settings=settings)
    if credential:
        source = "user_key"
        provider = credential.provider
        model = credential.model
    elif settings.ai_provider == "mock":
        source = "mock"
        provider = "mock"
        model = settings.ai_model
    else:
        source = "platform_free"
        provider = settings.ai_provider
        model = settings.ai_model
        if remaining_quota(account) < input_tokens + output_tokens:
            raise ApiError(
                "QUOTA_EXHAUSTED",
                "平台免费额度不足，请先连接自己的模型 Key。",
                402,
            )
    estimated_cost, pricing_configured = _estimate_cost(
        settings,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    requires_confirmation = source == "user_key" or (
        pricing_configured
        and estimated_cost >= settings.cost_confirmation_threshold_microusd
    )
    now = datetime.now(UTC)
    quote = CostAuthorization(
        owner_id=owner_id,
        project_id=project.id,
        credential_ref_id=credential.id if credential else None,
        operation=operation,
        provider=provider,
        model=model,
        source=source,
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_quota_units=input_tokens + output_tokens,
        estimated_cost_microusd=estimated_cost,
        pricing_configured=pricing_configured,
        requires_confirmation=requires_confirmation,
        status="pending" if requires_confirmation else "confirmed",
        expires_at=now + timedelta(minutes=15),
        confirmed_at=None if requires_confirmation else now,
    )
    db.add(quote)
    db.flush()
    return quote


def owned_cost_authorization(
    db: Session,
    *,
    authorization_id: str,
    owner_id: str,
    project_id: str | None = None,
) -> CostAuthorization:
    item = db.scalar(
        select(CostAuthorization).where(
            CostAuthorization.id == authorization_id,
            CostAuthorization.owner_id == owner_id,
        )
    )
    if not item or (project_id is not None and item.project_id != project_id):
        raise not_found("费用确认")
    if _aware(item.expires_at) <= datetime.now(UTC) and item.status in {"pending", "confirmed"}:
        item.status = "expired"
        db.flush()
    return item


def consume_authorization(
    db: Session,
    *,
    authorization_id: str,
    owner_id: str,
    project_id: str,
    operation: str,
    credential_id: str | None,
) -> CostAuthorization:
    item = owned_cost_authorization(
        db,
        authorization_id=authorization_id,
        owner_id=owner_id,
        project_id=project_id,
    )
    if item.operation != operation or item.credential_ref_id != credential_id:
        raise ApiError("COST_AUTHORIZATION_MISMATCH", "费用确认与当前操作不匹配。", 409)
    if item.status == "consumed":
        return item
    if item.status != "confirmed":
        raise ApiError("COST_CONFIRMATION_REQUIRED", "请先确认本次预计用量和费用。", 409)
    item.status = "consumed"
    item.consumed_at = datetime.now(UTC)
    return item


def record_usage(
    db: Session,
    *,
    settings: Settings,
    owner_id: str,
    project_id: str | None,
    task_id: str | None,
    credential: CredentialRef | None,
    operation: str,
    provider: str,
    model: str,
    usage: dict[str, object],
    trace_id: str,
) -> UsageLedger:
    prompt_tokens = max(int(usage.get("prompt_tokens") or 0), 0)
    completion_tokens = max(int(usage.get("completion_tokens") or 0), 0)
    total_tokens = max(int(usage.get("total_tokens") or prompt_tokens + completion_tokens), 0)
    is_mock = provider == "mock" or usage.get("provider_verification") == "mock" or (
        usage.get("source") == "generated_runtime"
    )
    source = "user_key" if credential else ("mock" if is_mock else "platform_free")
    cost, pricing_configured = _estimate_cost(
        settings,
        input_tokens=prompt_tokens,
        output_tokens=completion_tokens,
    )
    quota_units = total_tokens if source == "platform_free" else 0
    if quota_units:
        account = ensure_quota_account(db, user_id=owner_id, settings=settings)
        if remaining_quota(account) < quota_units:
            raise ApiError("QUOTA_EXHAUSTED", "平台免费额度已用完。", 402)
        account.consumed_units += quota_units
    item = UsageLedger(
        owner_id=owner_id,
        project_id=project_id,
        task_id=task_id,
        credential_ref_id=credential.id if credential else None,
        operation=operation,
        provider=provider,
        model=model,
        source=source,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        quota_units=quota_units,
        estimated_cost_microusd=cost,
        pricing_configured=pricing_configured,
        usage_json={
            key: value
            for key, value in usage.items()
            if key not in {"api_key", "authorization", "secret"}
        },
        trace_id=trace_id,
    )
    db.add(item)
    db.flush()
    return item
