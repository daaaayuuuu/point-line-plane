from __future__ import annotations

import hashlib
import hmac
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi import Request
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import secret_hash
from app.models import BackupRecord, BetaInvite, Deployment, Project, RateLimitEvent, Task
from app.schemas.contracts import BackupResponse, BetaInviteResponse, OperationsMetricsResponse


def require_operations_token(request: Request) -> None:
    expected = request.app.state.settings.operations_token.get_secret_value()
    candidate = request.headers.get("x-operations-token", "")
    if not candidate or not hmac.compare_digest(candidate, expected):
        raise ApiError("OPERATIONS_AUTH_REQUIRED", "运维凭证无效。", 401)


def enforce_rate_limit(
    db: Session,
    *,
    settings: Settings,
    action: str,
    client_key: str,
) -> None:
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.auth_rate_limit_window_seconds)
    key_hash = secret_hash(f"{action}:{client_key}")
    count = int(
        db.scalar(
            select(func.count(RateLimitEvent.id)).where(
                RateLimitEvent.key_hash == key_hash,
                RateLimitEvent.action == action,
                RateLimitEvent.occurred_at >= cutoff,
            )
        )
        or 0
    )
    if count >= settings.auth_rate_limit_attempts:
        raise ApiError("RATE_LIMITED", "尝试次数过多，请稍后再试。", 429)
    db.add(RateLimitEvent(key_hash=key_hash, action=action, occurred_at=now))
    db.execute(delete(RateLimitEvent).where(RateLimitEvent.occurred_at < now - timedelta(days=1)))
    db.flush()


def beta_invite_response(item: BetaInvite) -> BetaInviteResponse:
    return BetaInviteResponse(
        id=item.id,
        label=item.label,
        status=item.status,
        max_uses=item.max_uses,
        use_count=item.use_count,
        expires_at=item.expires_at,
        created_at=item.created_at,
    )


def backup_response(item: BackupRecord) -> BackupResponse:
    return BackupResponse(
        id=item.id,
        mode=item.mode,
        status=item.status,
        storage_ref=item.storage_ref,
        sha256=item.sha256,
        size_bytes=item.size_bytes,
        evidence=item.evidence_json,
        error_code=item.error_code,
        created_at=item.created_at,
        completed_at=item.completed_at,
    )


@dataclass(frozen=True, slots=True)
class BackupResult:
    storage_ref: str
    sha256: str | None
    size_bytes: int
    evidence: dict[str, Any]


def _sqlite_backup(settings: Settings) -> BackupResult:
    if not settings.database_url.startswith("sqlite:///"):
        raise ApiError("BACKUP_MODE_MISMATCH", "当前数据库不能使用 SQLite 备份模式。", 409)
    source = Path(settings.database_url.removeprefix("sqlite:///"))
    if not source.is_file():
        raise ApiError("BACKUP_SOURCE_MISSING", "数据库文件不存在。", 409)
    settings.backup_root.mkdir(parents=True, exist_ok=True)
    backup_id = str(uuid4())
    target = (settings.backup_root / f"{backup_id}.sqlite3").resolve()
    temporary = target.with_name(f".{target.name}.tmp")
    with sqlite3.connect(source) as source_db, sqlite3.connect(temporary) as target_db:
        source_db.backup(target_db)
        integrity = target_db.execute("PRAGMA integrity_check").fetchone()
    if not integrity or integrity[0] != "ok":
        temporary.unlink(missing_ok=True)
        raise ApiError("BACKUP_INTEGRITY_FAILED", "备份完整性校验失败。", 500)
    temporary.replace(target)
    raw = target.read_bytes()
    return BackupResult(
        storage_ref=str(target.relative_to(settings.backup_root.resolve())),
        sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        evidence={"integrity_check": "ok", "database_engine": "sqlite"},
    )


def _external_backup(settings: Settings) -> BackupResult:
    try:
        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{settings.backup_adapter_base_url.rstrip('/')}/v1/backups",
                headers={
                    "Authorization": f"Bearer {settings.backup_adapter_token.get_secret_value()}"
                },
                json={"database": "primary", "mode": "consistent_snapshot"},
            )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ApiError("BACKUP_ADAPTER_UNAVAILABLE", "备份服务暂时不可用。", 502) from exc
    if not isinstance(body, dict) or body.get("status") != "succeeded" or not body.get(
        "storage_ref"
    ):
        raise ApiError("BACKUP_INVALID_RESULT", "备份服务返回结果不完整。", 502)
    return BackupResult(
        storage_ref=str(body["storage_ref"])[:300],
        sha256=str(body["sha256"]) if body.get("sha256") else None,
        size_bytes=int(body.get("size_bytes") or 0),
        evidence=body.get("evidence") if isinstance(body.get("evidence"), dict) else {},
    )


def create_backup(db: Session, settings: Settings) -> BackupRecord:
    result = _sqlite_backup(settings) if settings.backup_mode == "sqlite_local" else _external_backup(settings)
    item = BackupRecord(
        mode=settings.backup_mode,
        status="succeeded",
        storage_ref=result.storage_ref,
        sha256=result.sha256,
        size_bytes=result.size_bytes,
        evidence_json=result.evidence,
        completed_at=datetime.now(UTC),
    )
    db.add(item)
    db.flush()
    return item


def operations_metrics(db: Session, database_url: str) -> OperationsMetricsResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    return OperationsMetricsResponse(
        database={
            "engine": "postgresql" if database_url.startswith("postgresql") else "sqlite",
            "reachable": db.scalar(select(text("1"))) == 1,
        },
        counts={
            "projects": int(db.scalar(select(func.count(Project.id))) or 0),
            "tasks": int(db.scalar(select(func.count(Task.id))) or 0),
            "deployments": int(db.scalar(select(func.count(Deployment.id))) or 0),
        },
        recent_failures={
            "tasks": int(
                db.scalar(
                    select(func.count(Task.id)).where(
                        Task.status == "failed", Task.updated_at >= cutoff
                    )
                )
                or 0
            ),
            "deployments": int(
                db.scalar(
                    select(func.count(Deployment.id)).where(
                        Deployment.status == "failed", Deployment.updated_at >= cutoff
                    )
                )
                or 0
            ),
        },
        generated_at=datetime.now(UTC),
    )
