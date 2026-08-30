from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import KNOWN_DEFAULT_INVITE_CODES, KNOWN_DEFAULT_SESSION_SECRETS
from app.models import AuditEvent, Preview, User
from tests.support import ApiHarness, assert_error


@pytest.mark.parametrize("default_secret", sorted(KNOWN_DEFAULT_SESSION_SECRETS))
def test_production_rejects_each_known_default_session_secret(
    settings_factory,
    default_secret: str,
) -> None:
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        settings_factory(
            app_env="production",
            auto_create_db=False,
            session_secret=default_secret,
            invite_codes="production-invite-credential-a",
        )


@pytest.mark.parametrize("default_invite", sorted(KNOWN_DEFAULT_INVITE_CODES))
def test_production_rejects_each_known_default_invite_code(
    settings_factory,
    default_invite: str,
) -> None:
    with pytest.raises(ValidationError, match="INVITE_CODES"):
        settings_factory(
            app_env="production",
            auto_create_db=False,
            session_secret="a-production-session-secret-with-more-than-32-characters",
            invite_codes=default_invite,
        )


def test_settings_reject_duplicate_invite_codes_after_normalization(settings_factory) -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        settings_factory(
            app_env="production",
            auto_create_db=False,
            session_secret="a-production-session-secret-with-more-than-32-characters",
            invite_codes="duplicate-code, duplicate-code",
        )


def test_one_invite_code_can_only_claim_one_user_identity(
    api: ApiHarness,
    client: TestClient,
    app: FastAPI,
) -> None:
    first_token, first_user = api.login("Invite Owner")

    claimed = client.post(
        "/api/v1/auth/invite-login",
        json={"invite_code": "test-invite", "display_name": "Different Person"},
    )
    assert_error(claimed, status_code=409, code="INVITE_CODE_ALREADY_CLAIMED")

    second_token, same_user = api.login("Invite Owner")
    assert second_token != first_token
    assert same_user["id"] == first_user["id"]
    with app.state.database.session_factory() as db:
        assert db.scalar(select(func.count(User.id))) == 1


def test_request_id_accepts_only_safe_database_length_and_characters(
    client: TestClient,
    app: FastAPI,
) -> None:
    safe_request_id = "request-id_2026.08.20-abcdefghijk"
    assert len(safe_request_id) <= 36
    safe = client.post(
        "/api/v1/auth/invite-login",
        json={"invite_code": "invalid", "display_name": "Trace User"},
        headers={"X-Request-ID": safe_request_id},
    )
    safe_error = assert_error(safe, status_code=401, code="INVALID_INVITE_CODE")
    assert safe_error["trace_id"] == safe_request_id

    unsafe_values = [
        "x" * 37,
        "-leading-separator",
        "contains a space",
        "contains/a/slash",
    ]
    generated_trace_ids: list[str] = []
    for value in unsafe_values:
        response = client.post(
            "/api/v1/auth/invite-login",
            json={"invite_code": "invalid", "display_name": "Trace User"},
            headers={"X-Request-ID": value},
        )
        error = assert_error(response, status_code=401, code="INVALID_INVITE_CODE")
        assert error["trace_id"] != value
        assert len(error["trace_id"]) == 36
        UUID(error["trace_id"])
        generated_trace_ids.append(error["trace_id"])

    with app.state.database.session_factory() as db:
        persisted = set(db.scalars(select(AuditEvent.trace_id)))
    assert safe_request_id in persisted
    assert set(generated_trace_ids) <= persisted
    assert all(len(value) <= 36 for value in persisted)


def test_code_version_commit_ref_resolves_to_a_real_controlled_workspace_commit(
    api: ApiHarness,
    settings,
) -> None:
    token, _user = api.login("Git Version User")
    project, _task, preview_token = api.build_preview(token)
    preview_response = api.client.get(f"/api/v1/previews/{preview_token}")
    assert preview_response.status_code == 200
    code_version = preview_response.json()["code_version"]
    commit_ref = code_version["commit_ref"]
    assert re.fullmatch(r"[0-9a-f]{40}", commit_ref)

    version_directory = settings.workspace_root / project["id"] / "repository"
    assert (version_directory / "product_factory.json").is_file()
    assert (version_directory / "app" / "main.py").is_file()
    resolved = subprocess.run(
        ["git", "-C", str(version_directory), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert resolved == commit_ref

    tracked_files = subprocess.run(
        ["git", "-C", str(version_directory), "show", "--format=", "--name-only", commit_ref],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert "product_factory.json" in tracked_files
    assert "app/main.py" in tracked_files


def test_expired_preview_is_not_advertised_as_ready_in_project_views(
    api: ApiHarness,
    client: TestClient,
    app: FastAPI,
) -> None:
    token, _user = api.login("Expired Preview User")
    project, _task, preview_token = api.build_preview(token)
    with app.state.database.session_factory() as db:
        preview = db.scalar(select(Preview).where(Preview.preview_token == preview_token))
        assert preview is not None
        preview.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        preview.status = "ready"
        db.commit()

    api.use_token(token)
    detail_response = client.get(f"/api/v1/projects/{project['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["preview"] is None
    assert detail["preview_token"] is None
    assert detail["next_action"]["code"] != "review_preview"

    list_response = client.get("/api/v1/projects")
    assert list_response.status_code == 200
    listed = next(item for item in list_response.json()["items"] if item["id"] == project["id"])
    assert listed["preview_token"] is None

    expired_response = client.get(f"/api/v1/previews/{preview_token}")
    assert_error(expired_response, status_code=410, code="PREVIEW_EXPIRED")
    with app.state.database.session_factory() as db:
        status = db.scalar(
            select(Preview.status).where(Preview.preview_token == preview_token)
        )
        assert status == "expired"
