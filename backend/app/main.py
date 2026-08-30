from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.database import Database
from app.core.errors import ApiError
from app.models import Base
from app.services.codex_auth import CodexAuthBridge
from app.services.codex_reasoning import CodexReasoningProgressStore
from app.services.credentials import SecretVault
from app.services.deployment import PersistentDeploymentRunner, build_deployment_adapter
from app.services.providers import build_provider
from app.services.quality_runtime import GeneratedPreviewManager
from app.services.task_runner import PersistentTaskRunner

logger = logging.getLogger("product_factory")
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,35}$")
STATIC_ROOT = Path(__file__).resolve().parent / "static"


def _error_payload(code: str, message: str, trace_id: str) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "trace_id": trace_id}}


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    database = Database(
        runtime_settings.database_url,
        sqlite_lock_timeout_seconds=runtime_settings.sqlite_lock_timeout_seconds,
        pool_size=runtime_settings.database_pool_size,
        max_overflow=runtime_settings.database_max_overflow,
        pool_timeout_seconds=runtime_settings.database_pool_timeout_seconds,
    )
    provider = build_provider(runtime_settings)
    codex_auth_bridge = CodexAuthBridge(
        command=runtime_settings.codex_command,
        auth_root=runtime_settings.codex_auth_root,
        request_timeout_seconds=runtime_settings.codex_request_timeout_seconds,
        login_timeout_seconds=runtime_settings.codex_login_timeout_seconds,
        turn_timeout_seconds=runtime_settings.codex_turn_timeout_seconds,
    )
    preview_manager = GeneratedPreviewManager(runtime_settings)
    secret_vault = SecretVault(runtime_settings)
    deployment_adapter = build_deployment_adapter(runtime_settings)
    deployment_runner = PersistentDeploymentRunner(
        database.session_factory,
        runtime_settings,
        secret_vault,
        deployment_adapter,
    )
    task_runner = PersistentTaskRunner(
        database.session_factory,
        runtime_settings,
        provider,
        preview_manager,
        secret_vault,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        runtime_settings.workspace_root.mkdir(parents=True, exist_ok=True)
        secret_vault.initialize()
        if runtime_settings.auto_create_db:
            Base.metadata.create_all(database.engine)
        preview_manager.recover(database.session_factory)
        task_runner.recover()
        deployment_runner.recover()
        yield
        codex_auth_bridge.shutdown()
        deployment_runner.shutdown()
        task_runner.shutdown()
        preview_manager.shutdown()
        database.engine.dispose()

    application = FastAPI(
        title="AI 产品工厂 API",
        version="0.8.0",
        docs_url="/docs" if runtime_settings.app_env.lower() != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.state.settings = runtime_settings
    application.state.codex_auth_bridge = codex_auth_bridge
    application.state.codex_reasoning_progress = CodexReasoningProgressStore()
    application.state.database = database
    application.state.task_runner = task_runner
    application.state.provider = provider
    application.state.preview_manager = preview_manager
    application.state.secret_vault = secret_vault
    application.state.deployment_adapter = deployment_adapter
    application.state.deployment_runner = deployment_runner
    application.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.origin_values,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Last-Event-ID",
            "X-Operations-Token",
            "X-Request-ID",
        ],
    )

    @application.middleware("http")
    async def attach_trace_id(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request.state.trace_id = incoming if SAFE_REQUEST_ID.fullmatch(incoming) else str(uuid4())
        response = await call_next(request)
        response.headers["X-Trace-ID"] = request.state.trace_id
        return response

    @application.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        trace = getattr(request.state, "trace_id", str(uuid4()))
        logger.warning(
            "api_error trace_id=%s code=%s path=%s",
            trace,
            exc.code,
            request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc.code, exc.message, trace),
            headers={"X-Trace-ID": trace},
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        trace = getattr(request.state, "trace_id", str(uuid4()))
        return JSONResponse(
            status_code=422,
            content=_error_payload("VALIDATION_ERROR", "请求内容不符合接口要求。", trace),
            headers={"X-Trace-ID": trace},
        )

    @application.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        trace = getattr(request.state, "trace_id", str(uuid4()))
        message = exc.detail if isinstance(exc.detail, str) else "请求无法处理。"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload("HTTP_ERROR", message, trace),
            headers={"X-Trace-ID": trace},
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        trace = getattr(request.state, "trace_id", str(uuid4()))
        logger.error("unhandled request error trace_id=%s error_type=%s", trace, type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content=_error_payload("INTERNAL_ERROR", "系统暂时无法处理请求，请稍后重试。", trace),
            headers={"X-Trace-ID": trace},
        )

    application.include_router(router)
    if STATIC_ROOT.is_dir():
        application.mount("/test-ui", StaticFiles(directory=STATIC_ROOT, html=True), name="test-ui")
    return application


app = create_app()
