from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.support import assert_error


def _ops_headers(settings) -> dict[str, str]:
    return {"X-Operations-Token": settings.operations_token.get_secret_value()}


def test_frontend_cors_allows_operations_header(client) -> None:
    response = client.options(
        "/api/v1/operations/metrics",
        headers={
            "Origin": "http://testserver",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-operations-token",
        },
    )
    assert response.status_code == 200, response.text
    allowed = response.headers.get("access-control-allow-headers", "").lower()
    assert "x-operations-token" in allowed


def test_persistent_beta_invite_is_claimed_without_leaking_code(client, settings) -> None:
    code = "beta-invite-code-2026-alpha"
    created = client.post(
        "/api/v1/operations/beta-invites",
        headers=_ops_headers(settings),
        json={"code": code, "label": "Alpha cohort", "max_uses": 1},
    )
    assert created.status_code == 201, created.text
    assert code not in created.text
    assert "code_hash" not in created.text

    login = client.post(
        "/api/v1/auth/invite-login",
        json={"invite_code": code, "display_name": "Beta User"},
    )
    assert login.status_code == 200, login.text
    listed = client.get("/api/v1/operations/beta-invites", headers=_ops_headers(settings))
    assert listed.status_code == 200
    assert listed.json()[0]["status"] == "claimed"
    assert listed.json()[0]["use_count"] == 1

    impersonation = client.post(
        "/api/v1/auth/invite-login",
        json={"invite_code": code, "display_name": "Other User"},
    )
    assert_error(impersonation, status_code=409, code="INVITE_CODE_ALREADY_CLAIMED")


def test_invite_login_rate_limit_persists_in_database(settings_factory) -> None:
    settings = settings_factory(auth_rate_limit_attempts=2)
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        for index in range(2):
            rejected = client.post(
                "/api/v1/auth/invite-login",
                json={"invite_code": f"invalid-{index}", "display_name": "Rate User"},
            )
            assert_error(rejected, status_code=401, code="INVALID_INVITE_CODE")
        limited = client.post(
            "/api/v1/auth/invite-login",
            json={"invite_code": "invalid-final", "display_name": "Rate User"},
        )
        assert_error(limited, status_code=429, code="RATE_LIMITED")


def test_sqlite_backup_is_real_verified_and_ops_protected(client, settings) -> None:
    unauthorized = client.post("/api/v1/operations/backups", json={"confirm": True})
    assert_error(unauthorized, status_code=401, code="OPERATIONS_AUTH_REQUIRED")
    created = client.post(
        "/api/v1/operations/backups",
        headers=_ops_headers(settings),
        json={"confirm": True},
    )
    assert created.status_code == 201, created.text
    backup = created.json()
    assert backup["status"] == "succeeded"
    assert backup["evidence"]["integrity_check"] == "ok"
    path = settings.backup_root / backup["storage_ref"]
    assert path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == backup["sha256"]

    metrics = client.get("/api/v1/operations/metrics", headers=_ops_headers(settings))
    assert metrics.status_code == 200, metrics.text
    assert metrics.json()["database"]["reachable"] is True


def test_production_requires_postgresql_external_backup_and_ops_secret(settings_factory) -> None:
    common = {
        "app_env": "production",
        "auto_create_db": False,
        "session_secret": "production-session-secret-with-more-than-32-characters",
        "invite_codes": "production-invite-code-not-a-default",
        "credential_master_key": "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE=",
        "operations_token": "strong-production-operations-token-value",
    }
    try:
        settings_factory(**common)
    except ValueError as exc:
        assert "PostgreSQL" in str(exc) or "BACKUP_MODE" in str(exc)
    else:
        raise AssertionError("production settings accepted SQLite/local backup")


def test_backup_root_stays_inside_test_directory(settings) -> None:
    assert isinstance(settings.backup_root, Path)
    assert "backups-" in settings.backup_root.name
