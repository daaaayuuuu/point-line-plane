from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings


def assert_error(
    response: Any,
    *,
    status_code: int,
    code: str | set[str],
) -> dict[str, str]:
    """Assert the public error envelope without coupling to product copy."""
    assert response.status_code == status_code, response.text
    payload = response.json()
    assert set(payload) == {"error"}
    error = payload["error"]
    assert set(error) == {"code", "message", "trace_id"}
    expected_codes = {code} if isinstance(code, str) else code
    assert error["code"] in expected_codes
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["trace_id"], str) and error["trace_id"]
    assert response.headers["x-trace-id"] == error["trace_id"]
    return error


def sse_event_names(payload: str) -> list[str]:
    return [line.removeprefix("event: ") for line in payload.splitlines() if line.startswith("event: ")]


def sse_event_ids(payload: str) -> list[int]:
    return [int(line.removeprefix("id: ")) for line in payload.splitlines() if line.startswith("id: ")]


@dataclass(slots=True)
class ApiHarness:
    client: TestClient
    settings: Settings

    def use_token(self, token: str | None) -> None:
        self.client.cookies.clear()
        if token is not None:
            self.client.cookies.set(
                self.settings.session_cookie_name,
                token,
                domain="testserver.local",
                path="/",
            )

    def login(self, display_name: str = "测试用户", invite_code: str = "test-invite") -> tuple[str, dict[str, Any]]:
        self.client.cookies.clear()
        response = self.client.post(
            "/api/v1/auth/invite-login",
            json={"invite_code": invite_code, "display_name": display_name},
        )
        assert response.status_code == 200, response.text
        token = response.cookies.get(self.settings.session_cookie_name)
        assert token
        return token, response.json()["user"]

    def create_project(
        self,
        token: str,
        *,
        name: str = "文本洞察 Agent",
        idea: str = "帮助产品经理把访谈记录整理成结构化洞察",
    ) -> dict[str, Any]:
        self.use_token(token)
        response = self.client.post("/api/v1/projects", json={"name": name, "idea": idea})
        assert response.status_code == 201, response.text
        return response.json()

    def create_prd(
        self,
        token: str,
        project_id: str,
        *,
        message: str = "面向独立产品经理，输出摘要、关键洞察和下一步，结果可复制即算可用。",
    ) -> dict[str, Any]:
        self.use_token(token)
        project_response = self.client.get(f"/api/v1/projects/{project_id}")
        assert project_response.status_code == 200, project_response.text
        current_questions = project_response.json()["next_action"]["questions"]
        assert len(current_questions) == 1
        question_id = current_questions[0]["id"]
        next_message = message
        for _round in range(8):
            response = self.client.post(
                f"/api/v1/projects/{project_id}/requirements/messages",
                json={"message": next_message, "question_id": question_id},
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            if payload["status"] == "prd_ready":
                assert payload["artifact"] is not None
                return payload["artifact"]
            assert payload["status"] == "question"
            assert payload["artifact"] is None
            assert len(payload["questions"]) == 1
            question_id = payload["questions"][0]["id"]
            next_message = f"针对 {question_id} 的首版明确回答"
        raise AssertionError("requirements did not produce a PRD within the bounded question rounds")

    def prepare_solution_review(self, token: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        project = self.create_project(token)
        prd = self.create_prd(token, project["id"])
        response = self.client.post(
            f"/api/v1/projects/{project['id']}/confirmations/prd",
            json={"artifact_id": prd["id"], "decision": "confirm"},
        )
        assert response.status_code == 200, response.text
        solution = response.json()["next_artifact"]
        assert solution and solution["type"] == "solution"
        return project, prd, solution

    def prepare_development(self, token: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        project, prd, solution = self.prepare_solution_review(token)
        response = self.client.post(
            f"/api/v1/projects/{project['id']}/confirmations/solution",
            json={"artifact_id": solution["id"], "decision": "confirm"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["project"]["stage"] == "DEVELOPMENT"
        return project, prd, solution

    def start_development(self, token: str, project_id: str) -> dict[str, Any]:
        self.use_token(token)
        response = self.client.post(f"/api/v1/projects/{project_id}/development/start")
        assert response.status_code == 200, response.text
        return response.json()

    def wait_for_task(
        self,
        token: str,
        task_id: str,
        *,
        expected: set[str] | None = None,
        timeout_seconds: float = 15.0,
    ) -> dict[str, Any]:
        expected = expected or {"succeeded", "failed"}
        deadline = time.monotonic() + timeout_seconds
        last: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            self.use_token(token)
            response = self.client.get(f"/api/v1/tasks/{task_id}")
            assert response.status_code == 200, response.text
            last = response.json()
            if last["status"] in expected:
                return last
            time.sleep(0.01)
        raise AssertionError(f"task {task_id} did not reach {sorted(expected)}; last={last}")

    def build_preview(self, token: str) -> tuple[dict[str, Any], dict[str, Any], str]:
        project, _prd, _solution = self.prepare_development(token)
        task = self.start_development(token, project["id"])
        finished = self.wait_for_task(token, task["id"], expected={"succeeded"})
        self.use_token(token)
        detail_response = self.client.get(f"/api/v1/projects/{project['id']}")
        assert detail_response.status_code == 200, detail_response.text
        detail = detail_response.json()
        assert detail["stage"] == "PREVIEW_REVIEW"
        assert detail["preview"]
        return detail, finished, detail["preview"]["token"]
