from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import session_token_hash
from app.models import Session
from app.services.codex_auth import CodexAccount, CodexAuthBridge, CodexLoginAttempt
from tests.support import ApiHarness, assert_error


class FakeCodexAuthBridge:
    def __init__(self) -> None:
        self.logged_out = False

    def start_login(self) -> CodexLoginAttempt:
        return CodexLoginAttempt(
            attempt_id="11111111-1111-4111-8111-111111111111",
            status="pending",
            auth_url="https://chatgpt.com/official-login",
        )

    def login_status(self, attempt_id: str) -> CodexLoginAttempt:
        return CodexLoginAttempt(
            attempt_id=attempt_id,
            status="authenticated",
            account=CodexAccount(
                email="alice@example.com",
                plan_type="plus",
                display_name="Alice Example",
            ),
        )

    def read_account(self, *, refresh_token: bool) -> CodexAccount:
        return CodexAccount(
            email="alice@example.com",
            plan_type="plus",
            display_name="Alice Example",
        )

    def logout(self) -> None:
        self.logged_out = True


def test_codex_account_display_name_comes_from_matching_identity_claim(tmp_path: Path) -> None:
    payload = base64.urlsafe_b64encode(
        json.dumps({"email": "alice@example.com", "name": "  Alice   Example  "}).encode()
    ).decode().rstrip("=")
    (tmp_path / "auth.json").write_text(
        json.dumps({"tokens": {"id_token": f"header.{payload}.signature"}}),
        encoding="utf-8",
    )
    bridge = CodexAuthBridge(command="codex", auth_root=tmp_path)

    assert bridge._read_display_name(expected_email="alice@example.com") == "Alice Example"
    assert bridge._read_display_name(expected_email="other@example.com") is None


def test_codex_turn_streams_detailed_reasoning_summary_deltas(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bridge = CodexAuthBridge(command="codex", auth_root=tmp_path)
    observed_params: dict[str, object] = {}

    def fake_request(method: str, params: dict, **_kwargs):
        assert method == "turn/start"
        observed_params.update(params)
        event_queue = bridge._thread_streams["thread-1"][0]
        event_queue.put(
            {
                "method": "item/reasoning/summaryTextDelta",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "itemId": "reasoning-1",
                    "summaryIndex": 0,
                    "delta": "正在分析目标用户。",
                },
            }
        )
        event_queue.put(
            {
                "method": "item/reasoning/summaryPartAdded",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "itemId": "reasoning-1",
                    "summaryIndex": 1,
                },
            }
        )
        event_queue.put(
            {
                "method": "item/reasoning/summaryTextDelta",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "itemId": "reasoning-1",
                    "summaryIndex": 1,
                    "delta": "正在检查首版范围。",
                },
            }
        )
        event_queue.put(
            {
                "method": "item/completed",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": {"type": "agentMessage", "text": "done"},
                },
            }
        )
        event_queue.put(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "completed"},
                },
            }
        )
        return {"turn": {"id": "turn-1"}}

    monkeypatch.setattr(bridge, "_request", fake_request)
    summaries: list[str] = []
    result = bridge.run_turn(
        "thread-1",
        "做一个产品",
        on_reasoning_summary=summaries.append,
        model="gpt-5.6-sol",
        reasoning_effort="medium",
    )

    assert observed_params["summary"] == "detailed"
    assert observed_params["model"] == "gpt-5.6-sol"
    assert observed_params["effort"] == "medium"
    assert summaries == ["正在分析目标用户。", "\n", "正在检查首版范围。"]
    assert result.text == "done"


def test_codex_turn_uses_completed_reasoning_summary_when_no_delta_arrives(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bridge = CodexAuthBridge(command="codex", auth_root=tmp_path)

    def fake_request(method: str, _params: dict, **_kwargs):
        assert method == "turn/start"
        event_queue = bridge._thread_streams["thread-1"][0]
        event_queue.put(
            {
                "method": "item/completed",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": {
                        "type": "reasoning",
                        "summary": ["先识别目标用户。", "再梳理核心流程。"],
                    },
                },
            }
        )
        event_queue.put(
            {
                "method": "item/completed",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": {"type": "agentMessage", "text": "done"},
                },
            }
        )
        event_queue.put(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "completed"},
                },
            }
        )
        return {"turn": {"id": "turn-1"}}

    monkeypatch.setattr(bridge, "_request", fake_request)
    summaries: list[str] = []
    result = bridge.run_turn(
        "thread-1",
        "做一个产品",
        on_reasoning_summary=summaries.append,
    )

    assert summaries == ["先识别目标用户。\n再梳理核心流程。"]
    assert result.text == "done"


def test_invite_login_session_identity_and_logout(
    api: ApiHarness,
    client: TestClient,
    settings,
) -> None:
    invalid = client.post(
        "/api/v1/auth/invite-login",
        json={"invite_code": "wrong-code", "display_name": "Alice"},
        headers={"X-Request-ID": "invalid-invite-trace"},
    )
    error = assert_error(invalid, status_code=401, code="INVALID_INVITE_CODE")
    assert error["trace_id"] == "invalid-invite-trace"

    valid = client.post(
        "/api/v1/auth/invite-login",
        json={"invite_code": "test-invite", "display_name": "Alice"},
    )
    assert valid.status_code == 200
    token = client.cookies.get(settings.session_cookie_name)
    assert token
    user = valid.json()["user"]
    set_cookie = valid.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "secure" not in set_cookie

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["id"] == user["id"]
    assert token not in me.text

    second_token, same_user = api.login("Alice")
    assert second_token != token
    assert same_user["id"] == user["id"]

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    assert logout.json() == {"ok": True}

    api.use_token(second_token)
    invalidated = client.get("/api/v1/auth/me")
    assert_error(invalidated, status_code=401, code="INVALID_SESSION")

    api.use_token(token)
    still_valid = client.get("/api/v1/auth/me")
    assert still_valid.status_code == 200


def test_codex_login_creates_product_session_and_logs_out(
    app: FastAPI,
    client: TestClient,
    settings,
) -> None:
    bridge = FakeCodexAuthBridge()
    app.state.codex_auth_bridge = bridge

    started = client.post("/api/v1/auth/codex/start")
    assert started.status_code == 200, started.text
    assert started.json() == {
        "attempt_id": "11111111-1111-4111-8111-111111111111",
        "status": "pending",
        "auth_url": "https://chatgpt.com/official-login",
        "account": None,
        "error": None,
    }

    completed = client.get(
        "/api/v1/auth/codex/status",
        params={"attempt_id": started.json()["attempt_id"]},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "authenticated"
    assert completed.json()["account"] == {
        "email": "alice@example.com",
        "plan_type": "plus",
        "display_name": "Alice Example",
    }
    assert client.cookies.get(settings.session_cookie_name)

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["user"]["display_name"] == "Alice Example"
    assert me.json()["user"]["quota"]["auth_provider"] == "codex"
    assert me.json()["user"]["quota"]["codex_plan_type"] == "plus"

    logged_out = client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 200, logged_out.text
    assert bridge.logged_out is True


def test_expired_session_is_rejected_and_removed(
    api: ApiHarness,
    client: TestClient,
    app: FastAPI,
    settings,
) -> None:
    token, _user = api.login("Expired User")
    digest = session_token_hash(token, settings.session_secret.get_secret_value())
    with app.state.database.session_factory() as db:
        session = db.scalar(select(Session).where(Session.token_hash == digest))
        assert session is not None
        session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session_id = session.id
        db.commit()

    response = client.get("/api/v1/auth/me")
    assert_error(response, status_code=401, code="SESSION_EXPIRED")
    with app.state.database.session_factory() as db:
        assert db.get(Session, session_id) is None


def test_authentication_is_required(api: ApiHarness, client: TestClient) -> None:
    api.use_token(None)
    response = client.get("/api/v1/projects")
    assert_error(response, status_code=401, code="AUTH_REQUIRED")


def test_frontend_cors_allows_project_delete(client: TestClient) -> None:
    response = client.options(
        "/api/v1/projects/example-project-id",
        headers={
            "Origin": "http://testserver",
            "Access-Control-Request-Method": "DELETE",
        },
    )
    assert response.status_code == 200, response.text
    allowed = response.headers.get("access-control-allow-methods", "").lower()
    assert "delete" in allowed


def test_project_delete_requires_owner_and_removes_project(
    api: ApiHarness,
    client: TestClient,
) -> None:
    owner_token, _owner = api.login("Project Owner")
    project = api.create_project(owner_token, name="可删除测试项目")

    other_token, _other = api.login("Other User", invite_code="second-invite")
    api.use_token(other_token)
    denied = client.delete(f"/api/v1/projects/{project['id']}")
    assert_error(denied, status_code=404, code="NOT_FOUND")

    api.use_token(owner_token)
    deleted = client.delete(f"/api/v1/projects/{project['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}

    projects = client.get("/api/v1/projects")
    assert projects.status_code == 200
    assert all(item["id"] != project["id"] for item in projects.json()["items"])
    assert_error(
        client.get(f"/api/v1/projects/{project['id']}"),
        status_code=404,
        code="NOT_FOUND",
    )


def test_project_artifact_task_and_preview_are_tenant_isolated(
    api: ApiHarness,
    client: TestClient,
) -> None:
    alice_token, _alice = api.login("Alice Tenant")
    alice_project, _task, preview_token = api.build_preview(alice_token)
    project_id = alice_project["id"]
    artifact_id = alice_project["latest_artifacts"][0]["id"]
    task_id = alice_project["active_task"]["id"]

    bob_token, _bob = api.login("Bob Tenant", invite_code="second-invite")
    api.use_token(bob_token)
    projects = client.get("/api/v1/projects")
    assert projects.status_code == 200
    assert projects.json()["items"] == []

    denied_requests = [
        client.get(f"/api/v1/projects/{project_id}"),
        client.get(f"/api/v1/artifacts/{artifact_id}"),
        client.get(f"/api/v1/tasks/{task_id}"),
        client.get(f"/api/v1/tasks/{task_id}/events"),
        client.get(f"/api/v1/previews/{preview_token}"),
        client.delete(f"/api/v1/projects/{project_id}"),
        client.post(
            f"/api/v1/previews/{preview_token}/runs",
            json={"input": "attempt to use another tenant preview"},
        ),
        client.post(
            f"/api/v1/projects/{project_id}/preview-feedback",
            json={"feedback": "调整输出语气"},
        ),
    ]
    for response in denied_requests:
        assert_error(response, status_code=404, code="NOT_FOUND")

    api.use_token(alice_token)
    owner_can_still_read = client.get(f"/api/v1/projects/{project_id}")
    assert owner_can_still_read.status_code == 200

    deleted = client.delete(f"/api/v1/projects/{project_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert_error(
        client.get(f"/api/v1/projects/{project_id}"),
        status_code=404,
        code="NOT_FOUND",
    )
