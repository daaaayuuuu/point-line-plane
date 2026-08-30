from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError, not_found
from app.models import (
    CodeVersion,
    DeliveryPackage,
    Deployment,
    GithubSync,
    Project,
    QualityRun,
)
from app.schemas.contracts import DeliveryPackageResponse, GithubSyncResponse
from app.services.development_runtime import git_command, project_repository
from app.services.workflow import transition

DENIED_NAMES = {".env", ".env.local", "credentials.json", "secrets.json"}
DENIED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".key", ".pem", ".p12"}
SAFE_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _safe_archive_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", "..", ".git"} for part in path.parts)
        or path.name in DENIED_NAMES
        or path.suffix.lower() in DENIED_SUFFIXES
        or any(part.lower() in {"secret", "secrets", "credentials"} for part in path.parts[:-1])
    ):
        raise ApiError("DELIVERY_FILE_DENIED", "交付包中发现不允许导出的文件。", 409)
    return value


def delivery_response(item: DeliveryPackage) -> DeliveryPackageResponse:
    return DeliveryPackageResponse(
        id=item.id,
        project_id=item.project_id,
        deployment_id=item.deployment_id,
        code_version_id=item.code_version_id,
        revision=item.revision,
        status=item.status,
        filename=item.filename,
        sha256=item.sha256,
        size_bytes=item.size_bytes,
        manifest=item.manifest_json,
        download_url=f"/api/v1/delivery-packages/{item.id}/download",
        created_at=item.created_at,
    )


def github_sync_response(item: GithubSync) -> GithubSyncResponse:
    return GithubSyncResponse(
        id=item.id,
        project_id=item.project_id,
        delivery_package_id=item.delivery_package_id,
        repository_full_name=item.repository_full_name,
        branch=item.branch,
        status=item.status,
        provider_ref=item.provider_ref,
        repository_url=item.repository_url,
        evidence=item.evidence_json,
        error_code=item.error_code,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def owned_delivery(db: Session, package_id: str, owner_id: str) -> DeliveryPackage:
    item = db.scalar(
        select(DeliveryPackage)
        .join(Project, Project.id == DeliveryPackage.project_id)
        .where(DeliveryPackage.id == package_id, Project.owner_id == owner_id)
    )
    if not item:
        raise not_found("交付包")
    return item


def package_path(settings: Settings, item: DeliveryPackage) -> Path:
    root = settings.delivery_root.resolve()
    target = (root / item.storage_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ApiError("DELIVERY_PATH_INVALID", "交付包存储路径无效。", 500) from exc
    if not target.is_file():
        raise ApiError("DELIVERY_PACKAGE_MISSING", "交付包文件不存在。", 404)
    return target


def create_delivery_package(
    db: Session,
    *,
    settings: Settings,
    project: Project,
    deployment: Deployment,
) -> tuple[DeliveryPackage, bool]:
    existing = db.scalar(
        select(DeliveryPackage).where(DeliveryPackage.deployment_id == deployment.id)
    )
    if existing:
        return existing, False
    if deployment.status not in {"succeeded", "simulated"}:
        raise ApiError("DEPLOYMENT_NOT_READY", "部署流程尚未完成，不能生成交付包。", 409)
    code_version = db.get(CodeVersion, deployment.code_version_id)
    if not code_version or code_version.test_status != "quality_passed":
        raise ApiError("DELIVERY_VERSION_INVALID", "交付版本没有通过质量门。", 409)
    repository = project_repository(settings, project.id)
    paths = [
        _safe_archive_path(value)
        for value in git_command(
            repository, "ls-tree", "-r", "--name-only", code_version.commit_ref
        ).stdout.splitlines()
        if value
    ]
    if not paths:
        raise ApiError("DELIVERY_SOURCE_EMPTY", "交付版本中没有可导出的源码。", 409)
    quality_runs = list(
        db.scalars(
            select(QualityRun)
            .where(QualityRun.code_version_id == code_version.id)
            .order_by(QualityRun.sequence)
        )
    )
    technical_doc = (
        f"# {project.name} 技术说明\n\n"
        f"- 交付代码版本：`{code_version.commit_ref}`\n"
        f"- 后端：Python 3.11 + FastAPI + Pydantic\n"
        f"- 质量状态：`{code_version.test_status}`\n"
        "- 所有凭证应通过环境变量或生产 Secret 管理器注入。\n"
    )
    test_lines = ["# 测试报告", "", f"版本：`{code_version.commit_ref}`", ""]
    for run in quality_runs:
        test_lines.append(
            f"- {run.kind}: {run.status}; exit_code={run.exit_code}; duration_ms={run.duration_ms:.0f}"
        )
    deployment_doc = (
        "# 部署说明\n\n"
        "1. 创建 Python 3.11 隔离环境。\n"
        "2. 安装 `pyproject.toml` 声明的依赖。\n"
        "3. 在 Secret 管理器中注入模型凭证，不要写入源码。\n"
        "4. 运行测试和健康检查后再切换流量。\n"
        "5. 本包未携带 `.env`、数据库、私钥或密钥。\n"
    )
    revision = int(
        db.scalar(
            select(func.max(DeliveryPackage.revision)).where(
                DeliveryPackage.project_id == project.id
            )
        )
        or 0
    ) + 1
    package_id = str(uuid4())
    relative = f"{project.id}/{package_id}.zip"
    target = (settings.delivery_root / relative).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    file_manifest: list[dict[str, Any]] = []
    total_source_bytes = 0
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            content = git_command(repository, "show", f"{code_version.commit_ref}:{path}").stdout
            raw = content.encode("utf-8")
            total_source_bytes += len(raw)
            if total_source_bytes > settings.delivery_max_bytes:
                raise ApiError("DELIVERY_PACKAGE_TOO_LARGE", "交付包超过当前大小上限。", 409)
            archive.writestr(f"source/{path}", raw)
            file_manifest.append(
                {"path": f"source/{path}", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            )
        for name, content in {
            "TECHNICAL_OVERVIEW.md": technical_doc,
            "TEST_REPORT.md": "\n".join(test_lines) + "\n",
            "DEPLOYMENT_GUIDE.md": deployment_doc,
        }.items():
            raw = content.encode("utf-8")
            archive.writestr(name, raw)
            file_manifest.append(
                {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            )
    size_bytes = temporary.stat().st_size
    if size_bytes > settings.delivery_max_bytes:
        temporary.unlink(missing_ok=True)
        raise ApiError("DELIVERY_PACKAGE_TOO_LARGE", "交付包超过当前大小上限。", 409)
    sha256 = hashlib.sha256(temporary.read_bytes()).hexdigest()
    temporary.replace(target)
    item = DeliveryPackage(
        id=package_id,
        project_id=project.id,
        deployment_id=deployment.id,
        code_version_id=code_version.id,
        revision=revision,
        status="ready",
        storage_path=relative,
        filename=f"{project.id}-delivery-v{revision}.zip",
        sha256=sha256,
        size_bytes=size_bytes,
        manifest_json={
            "commit_ref": code_version.commit_ref,
            "deployment_status": deployment.status,
            "files": file_manifest,
            "excluded": [".git", ".env*", "databases", "private keys", "credentials"],
        },
    )
    db.add(item)
    if project.stage == "DEPLOYMENT":
        transition(project, "DELIVERY")
    db.flush()
    return item, True


@dataclass(frozen=True, slots=True)
class GithubSyncResult:
    status: str
    provider_ref: str
    repository_url: str | None
    evidence: dict[str, Any]


class GithubAdapter(Protocol):
    def sync(self, *, package: Path, repository: str, branch: str) -> GithubSyncResult: ...


class MockGithubAdapter:
    def sync(self, *, package: Path, repository: str, branch: str) -> GithubSyncResult:
        return GithubSyncResult(
            status="simulated",
            provider_ref=f"mock-github-{uuid4()}",
            repository_url=None,
            evidence={"mode": "mock", "repository_modified": False, "branch": branch},
        )


class ExternalGithubAdapter:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.github_adapter_base_url.rstrip("/")
        self.token = settings.github_adapter_token.get_secret_value()

    def sync(self, *, package: Path, repository: str, branch: str) -> GithubSyncResult:
        try:
            with package.open("rb") as payload, httpx.Client(timeout=120) as client:
                response = client.post(
                    f"{self.base_url}/v1/github-syncs",
                    headers={"Authorization": f"Bearer {self.token}"},
                    data={"repository": repository, "branch": branch},
                    files={"package": (package.name, payload, "application/zip")},
                )
            response.raise_for_status()
            body = response.json()
        except (OSError, httpx.HTTPError, ValueError) as exc:
            raise ApiError("GITHUB_SYNC_UNAVAILABLE", "GitHub 同步服务暂时不可用。", 502) from exc
        url = body.get("repository_url") if isinstance(body, dict) else None
        provider_ref = body.get("provider_ref") if isinstance(body, dict) else None
        parsed = urlparse(url) if isinstance(url, str) else None
        if not provider_ref or not parsed or parsed.scheme != "https" or parsed.netloc != "github.com":
            raise ApiError("GITHUB_SYNC_INVALID_RESULT", "GitHub 同步结果不完整。", 502)
        return GithubSyncResult(
            status="succeeded",
            provider_ref=str(provider_ref),
            repository_url=url,
            evidence=body.get("evidence") if isinstance(body.get("evidence"), dict) else {},
        )


def build_github_adapter(settings: Settings) -> GithubAdapter:
    return MockGithubAdapter() if settings.github_sync_mode == "mock" else ExternalGithubAdapter(settings)


def sync_delivery_to_github(
    db: Session,
    *,
    settings: Settings,
    owner_id: str,
    package: DeliveryPackage,
    repository: str,
    branch: str,
) -> GithubSync:
    if not SAFE_REPOSITORY.fullmatch(repository):
        raise ApiError("GITHUB_REPOSITORY_INVALID", "GitHub 仓库名格式不正确。", 422)
    result = build_github_adapter(settings).sync(
        package=package_path(settings, package), repository=repository, branch=branch
    )
    item = GithubSync(
        owner_id=owner_id,
        project_id=package.project_id,
        delivery_package_id=package.id,
        repository_full_name=repository,
        branch=branch,
        status=result.status,
        provider_ref=result.provider_ref,
        repository_url=result.repository_url,
        evidence_json=result.evidence,
    )
    db.add(item)
    db.flush()
    return item
