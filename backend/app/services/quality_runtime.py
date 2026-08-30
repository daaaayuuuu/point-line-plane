from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.services.development_runtime import project_repository

OUTPUT_LIMIT = 16_000
SECRET_OUTPUT_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)(api[_-]?key|authorization|password)\s*[:=]\s*\S+"),
)


class QualityRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CommandResult:
    status: str
    exit_code: int | None
    duration_ms: float
    output_excerpt: str


@dataclass(frozen=True, slots=True)
class RuntimeHandle:
    process_ref: str
    host: str
    port: int
    base_url: str


def _safe_environment(repository: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONPATH": str(repository),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PRODUCT_AGENT_PROVIDER": "mock",
    }


def _sanitize_output(value: str, repository: Path) -> str:
    cleaned = value.replace(str(repository), "<project-workspace>")
    for pattern in SECRET_OUTPUT_PATTERNS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    if len(cleaned) > OUTPUT_LIMIT:
        return cleaned[-OUTPUT_LIMIT:]
    return cleaned


def _ensure_execution_allowed(settings: Settings, provider: str | None) -> None:
    if settings.generated_execution_mode == "trusted_mock" and provider != "mock":
        raise QualityRuntimeError(
            "EXTERNAL_SANDBOX_REQUIRED",
            "真实模型生成的代码必须交给外部隔离运行环境执行。",
        )
    if settings.generated_execution_mode == "external":
        raise QualityRuntimeError(
            "EXTERNAL_EXECUTOR_NOT_CONNECTED",
            "外部隔离运行环境尚未连接。",
        )


def run_quality_command(
    *,
    settings: Settings,
    project_id: str,
    provider: str | None,
    kind: str,
) -> CommandResult:
    _ensure_execution_allowed(settings, provider)
    repository = project_repository(settings, project_id)
    commands: dict[str, list[str]] = {
        "compile": [sys.executable, "-m", "compileall", "-q", "app", "tests"],
        "pytest": [sys.executable, "-m", "pytest", "-q"],
    }
    command = commands.get(kind)
    if not command:
        raise QualityRuntimeError("QUALITY_COMMAND_DENIED", "质量检查命令不在白名单中。")
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=repository,
            env=_safe_environment(repository),
            check=False,
            capture_output=True,
            text=True,
            timeout=settings.quality_command_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(part for part in (exc.stdout or "", exc.stderr or "") if part)
        return CommandResult(
            status="timed_out",
            exit_code=None,
            duration_ms=(time.monotonic() - started) * 1000,
            output_excerpt=_sanitize_output(output, repository),
        )
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    return CommandResult(
        status="passed" if result.returncode == 0 else "failed",
        exit_code=result.returncode,
        duration_ms=(time.monotonic() - started) * 1000,
        output_excerpt=_sanitize_output(output, repository),
    )


class GeneratedPreviewManager:
    """Owns local preview subprocesses for trusted deterministic bundles only."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen[bytes]] = {}

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return int(listener.getsockname()[1])

    def start(
        self,
        *,
        process_ref: str,
        project_id: str,
        provider: str | None,
    ) -> RuntimeHandle:
        _ensure_execution_allowed(self.settings, provider)
        with self._lock:
            existing = self._processes.get(process_ref)
            if existing and existing.poll() is None:
                raise QualityRuntimeError("PREVIEW_ALREADY_RUNNING", "预览进程已经启动。")
        repository = project_repository(self.settings, project_id)
        port = self._free_port()
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-access-log",
                ],
                cwd=repository,
                env=_safe_environment(repository),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise QualityRuntimeError("PREVIEW_START_FAILED", "无法启动生成应用预览。") from exc
        with self._lock:
            self._processes[process_ref] = process
        base_url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + self.settings.preview_startup_timeout_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                response = httpx.get(f"{base_url}/api/v1/health", timeout=0.5)
                if response.status_code == 200 and response.json().get("status") == "ok":
                    return RuntimeHandle(
                        process_ref=process_ref,
                        host="127.0.0.1",
                        port=port,
                        base_url=base_url,
                    )
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
            time.sleep(0.05)
        self.stop(process_ref)
        raise QualityRuntimeError("PREVIEW_START_FAILED", "生成应用没有在时限内通过健康检查。") from last_error

    def stop(self, process_ref: str) -> None:
        with self._lock:
            process = self._processes.pop(process_ref, None)
        if not process or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

    def request(
        self,
        *,
        process_ref: str,
        base_url: str,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        timeout: float = 5,
    ) -> httpx.Response:
        with self._lock:
            process = self._processes.get(process_ref)
        if not process or process.poll() is not None:
            raise QualityRuntimeError("PREVIEW_RUNTIME_STOPPED", "生成应用预览当前未运行。")
        if method not in {"GET", "POST"} or not (
            path.startswith("/api/v1/") or (method == "GET" and path == "/")
        ):
            raise QualityRuntimeError("PREVIEW_REQUEST_DENIED", "预览请求不在允许范围内。")
        try:
            return httpx.request(
                method,
                f"{base_url}{path}",
                json=json_body,
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            raise QualityRuntimeError("PREVIEW_UNAVAILABLE", "生成应用预览暂时不可用。") from exc

    def smoke(self, handle: RuntimeHandle) -> tuple[CommandResult, dict[str, Any]]:
        started = time.monotonic()
        try:
            health = self.request(
                process_ref=handle.process_ref,
                base_url=handle.base_url,
                method="GET",
                path="/api/v1/health",
            )
            page = self.request(
                process_ref=handle.process_ref,
                base_url=handle.base_url,
                method="GET",
                path="/",
            )
            analyze = self.request(
                process_ref=handle.process_ref,
                base_url=handle.base_url,
                method="POST",
                path="/api/v1/analyze",
                json_body={"input": "一次真实的后端预览冒烟输入"},
            )
            history = self.request(
                process_ref=handle.process_ref,
                base_url=handle.base_url,
                method="GET",
                path="/api/v1/history",
            )
            payload = analyze.json()
            history_payload = history.json()
            passed = (
                health.status_code == 200
                and page.status_code == 200
                and "text/html" in page.headers.get("content-type", "")
                and 'data-product-preview="controlled-html-webapp-v1"' in page.text
                and analyze.status_code == 200
                and history.status_code == 200
                and isinstance(payload.get("summary"), str)
                and isinstance(payload.get("key_points"), list)
                and isinstance(history_payload, list)
                and len(history_payload) >= 1
            )
            summary = {
                "health_status": health.status_code,
                "page_status": page.status_code,
                "html_product_marker": 'data-product-preview="controlled-html-webapp-v1"' in page.text,
                "analyze_status": analyze.status_code,
                "history_status": history.status_code,
                "history_count": len(history_payload) if isinstance(history_payload, list) else 0,
            }
            return (
                CommandResult(
                    status="passed" if passed else "failed",
                    exit_code=0 if passed else 1,
                    duration_ms=(time.monotonic() - started) * 1000,
                    output_excerpt="生成应用健康检查、真实 HTTP 输入和历史恢复均已执行。",
                ),
                summary,
            )
        except (QualityRuntimeError, ValueError) as exc:
            return (
                CommandResult(
                    status="failed",
                    exit_code=1,
                    duration_ms=(time.monotonic() - started) * 1000,
                    output_excerpt="生成应用没有通过真实 HTTP 冒烟。",
                ),
                {"error_code": getattr(exc, "code", "RUNTIME_SMOKE_FAILED")},
            )

    def shutdown(self) -> None:
        with self._lock:
            refs = list(self._processes)
        for process_ref in refs:
            self.stop(process_ref)

    def recover(self, session_factory: sessionmaker[Session]) -> None:
        from app.models import DevelopmentRun, Preview, PreviewRuntime

        with session_factory() as db:
            runtimes = list(
                db.scalars(
                    select(PreviewRuntime).where(PreviewRuntime.status == "ready")
                )
            )
            for runtime in runtimes:
                preview = db.get(Preview, runtime.preview_id)
                expires_at = preview.expires_at if preview else None
                if expires_at and expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                if not preview or not expires_at or expires_at <= datetime.now(UTC):
                    runtime.status = "expired"
                    runtime.stopped_at = datetime.now(UTC)
                    if preview:
                        preview.status = "expired"
                    continue
                development_run = db.scalar(
                    select(DevelopmentRun)
                    .where(DevelopmentRun.code_version_id == runtime.code_version_id)
                    .order_by(DevelopmentRun.created_at.desc())
                    .limit(1)
                )
                provider = development_run.provider if development_run else None
                try:
                    handle = self.start(
                        process_ref=runtime.process_ref,
                        project_id=runtime.project_id,
                        provider=provider,
                    )
                    runtime.host = handle.host
                    runtime.port = handle.port
                    runtime.base_url = handle.base_url
                    runtime.last_health_at = datetime.now(UTC)
                    runtime.error_code = None
                except QualityRuntimeError as exc:
                    runtime.status = "failed"
                    runtime.error_code = exc.code
                    runtime.stopped_at = datetime.now(UTC)
                    preview.status = "failed"
            db.commit()
