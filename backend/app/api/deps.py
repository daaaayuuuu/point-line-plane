from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DbSession

from app.core.config import Settings
from app.core.errors import ApiError, not_found
from app.core.security import session_token_hash
from app.models import Project, Session, User
from app.models.enums import ProjectStatus


def get_db(request: Request):
    db = request.app.state.database.session_factory()
    try:
        yield db
    finally:
        db.close()


Db = Annotated[DbSession, Depends(get_db)]


def settings_from_request(request: Request) -> Settings:
    return request.app.state.settings


def _is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)


def get_current_user(
    request: Request,
    db: Db,
    session_cookie: Annotated[str | None, Cookie(alias="product_factory_session")] = None,
) -> User:
    settings: Settings = request.app.state.settings
    actual_cookie = request.cookies.get(settings.session_cookie_name) or session_cookie
    if not actual_cookie:
        raise ApiError("AUTH_REQUIRED", "请先使用邀请码登录。", 401)
    token_hash = session_token_hash(actual_cookie, settings.session_secret.get_secret_value())
    login_session = db.scalar(select(Session).where(Session.token_hash == token_hash))
    if not login_session:
        raise ApiError("INVALID_SESSION", "登录状态无效，请重新登录。", 401)
    if _is_expired(login_session.expires_at):
        db.delete(login_session)
        db.commit()
        raise ApiError("SESSION_EXPIRED", "登录已过期，请重新登录。", 401)
    user = db.get(User, login_session.user_id)
    if not user:
        raise ApiError("INVALID_SESSION", "登录状态无效，请重新登录。", 401)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def _is_sqlite_lock_conflict(exc: OperationalError) -> bool:
    sqlite_errorcode = getattr(exc.orig, "sqlite_errorcode", None)
    if isinstance(sqlite_errorcode, int) and sqlite_errorcode & 0xFF in {5, 6}:
        return True
    message = str(exc.orig).lower()
    return "locked" in message or "busy" in message


def _begin_sqlite_immediate(db: DbSession) -> None:
    # Authentication SELECTs trigger SQLAlchemy's logical autobegin. Close that
    # read-only unit before acquiring SQLite's database-level reserved write lock.
    # A caller with pending writes has violated the lock-before-mutation contract;
    # never commit those changes implicitly while attempting to upgrade the lock.
    if db.new or db.dirty or db.deleted:
        raise ApiError(
            "PROJECT_WRITE_CONFLICT",
            "项目正在被修改，请刷新后重试。",
            409,
        )
    if db.in_transaction():
        db.commit()
    try:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    except OperationalError as exc:
        db.rollback()
        if _is_sqlite_lock_conflict(exc):
            raise ApiError(
                "PROJECT_WRITE_CONFLICT",
                "项目正在被其他请求修改，请稍后重试。",
                409,
            ) from None
        raise


def owned_project(db: DbSession, project_id: str, user_id: str, *, lock: bool = False) -> Project:
    statement = select(Project).where(
        Project.id == project_id,
        Project.owner_id == user_id,
        Project.status != ProjectStatus.DELETED.value,
    )
    dialect_name = db.get_bind().dialect.name
    if lock and dialect_name == "sqlite":
        _begin_sqlite_immediate(db)
    elif lock:
        statement = statement.with_for_update()
    try:
        project = db.scalar(statement)
    except OperationalError as exc:
        if lock and dialect_name == "sqlite" and _is_sqlite_lock_conflict(exc):
            db.rollback()
            raise ApiError(
                "PROJECT_WRITE_CONFLICT",
                "项目正在被其他请求修改，请稍后重试。",
                409,
            ) from None
        raise
    if not project:
        raise not_found("项目")
    return project
