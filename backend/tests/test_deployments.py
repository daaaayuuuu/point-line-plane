from __future__ import annotations

import time

from tests.support import assert_error


def _wait_for_deployment(api, deployment_id: str) -> dict:
    deadline = time.monotonic() + 5
    last = None
    while time.monotonic() < deadline:
        response = api.client.get(f"/api/v1/deployments/{deployment_id}")
        assert response.status_code == 200, response.text
        last = response.json()
        if last["status"] in {"simulated", "succeeded", "failed"}:
            return last
        time.sleep(0.01)
    raise AssertionError(f"deployment did not finish: {last}")


def _accept_and_connect(api, token: str) -> tuple[dict, dict]:
    project, _task, preview_token = api.build_preview(token)
    incomplete = api.client.post(
        f"/api/v1/previews/{preview_token}/acceptance",
        json={
            "core_flow_works": True,
            "result_is_useful": True,
            "history_persists": True,
            "errors_are_understandable": False,
        },
    )
    assert_error(incomplete, status_code=409, code="PREVIEW_CHECKLIST_INCOMPLETE")
    accepted = api.client.post(
        f"/api/v1/previews/{preview_token}/acceptance",
        json={
            "core_flow_works": True,
            "result_is_useful": True,
            "history_persists": True,
            "errors_are_understandable": True,
        },
    )
    assert accepted.status_code == 200, accepted.text
    detail = api.client.get(f"/api/v1/projects/{project['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["preview_accepted"] is True
    connected = api.client.post(
        "/api/v1/cloud-credentials",
        json={
            "provider": "volcano_engine",
            "access_key_id": "AKLT_TEST_ONLY_123456",
            "secret_access_key": "test-secret-never-returned-123456",
            "project_id": project["id"],
        },
    )
    assert connected.status_code == 201, connected.text
    assert "test-secret-never-returned" not in connected.text
    assert "secret_ref" not in connected.text
    return project, connected.json()


def test_deployment_requires_confirmation_and_mock_is_honest(api) -> None:
    token, _user = api.login()
    capabilities = api.client.get("/api/v1/capabilities")
    assert capabilities.status_code == 200, capabilities.text
    assert capabilities.json() == {
        "ai_provider_mode": "mock",
        "ai_provider": "mock",
        "ai_model": "mock-text-agent-test",
        "generated_execution_mode": "trusted_mock",
        "deployment_enabled": True,
        "deployment_mode": "mock",
        "deployment_provider": "volcano_engine",
        "deployment_region": "cn-beijing",
        "github_sync_mode": "mock",
    }
    project, credential = _accept_and_connect(api, token)
    credential_list = api.client.get(
        f"/api/v1/cloud-credentials?project_id={project['id']}"
    )
    assert credential_list.status_code == 200, credential_list.text
    assert credential_list.json()["items"][0]["id"] == credential["id"]
    quoted = api.client.post(
        f"/api/v1/projects/{project['id']}/deployment-authorizations",
        json={"credential_id": credential["id"], "action": "deploy"},
    )
    assert quoted.status_code == 201, quoted.text
    quote = quoted.json()
    assert quote["status"] == "pending"
    assert quote["estimated_cost"]["pricing_configured"] is False
    authorization_list = api.client.get(
        f"/api/v1/projects/{project['id']}/deployment-authorizations"
    )
    assert authorization_list.status_code == 200, authorization_list.text
    assert authorization_list.json()["items"][0]["id"] == quote["id"]

    blocked = api.client.post(
        f"/api/v1/projects/{project['id']}/deployments",
        json={"authorization_id": quote["id"]},
    )
    assert_error(blocked, status_code=409, code="DEPLOYMENT_AUTHORIZATION_REQUIRED")

    confirmed = api.client.post(
        f"/api/v1/deployment-authorizations/{quote['id']}/confirm",
        json={"confirm": True},
    )
    assert confirmed.status_code == 200, confirmed.text
    started = api.client.post(
        f"/api/v1/projects/{project['id']}/deployments",
        json={"authorization_id": quote["id"]},
    )
    assert started.status_code == 202, started.text
    finished = _wait_for_deployment(api, started.json()["id"])
    assert finished["status"] == "simulated"
    assert finished["deployment_url"] is None
    assert finished["evidence"]["created_cloud_resources"] is False
    assert finished["checkpoint"]["last_completed_step"] == "deployment_verified"

    listed = api.client.get(f"/api/v1/projects/{project['id']}/deployments")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == finished["id"]


def test_mock_rollback_is_authorized_and_traceable(api) -> None:
    token, _user = api.login("回滚用户", "second-invite")
    project, credential = _accept_and_connect(api, token)
    deploy_quote = api.client.post(
        f"/api/v1/projects/{project['id']}/deployment-authorizations",
        json={"credential_id": credential["id"], "action": "deploy"},
    ).json()
    api.client.post(
        f"/api/v1/deployment-authorizations/{deploy_quote['id']}/confirm",
        json={"confirm": True},
    )
    deployed = api.client.post(
        f"/api/v1/projects/{project['id']}/deployments",
        json={"authorization_id": deploy_quote["id"]},
    ).json()
    first = _wait_for_deployment(api, deployed["id"])

    rollback_quote_response = api.client.post(
        f"/api/v1/projects/{project['id']}/deployment-authorizations",
        json={
            "credential_id": credential["id"],
            "action": "rollback",
            "target_deployment_id": first["id"],
        },
    )
    assert rollback_quote_response.status_code == 201, rollback_quote_response.text
    rollback_quote = rollback_quote_response.json()
    api.client.post(
        f"/api/v1/deployment-authorizations/{rollback_quote['id']}/confirm",
        json={"confirm": True},
    )
    rolled_back_response = api.client.post(
        f"/api/v1/deployments/{first['id']}/rollback",
        json={"authorization_id": rollback_quote["id"], "confirm": True},
    )
    assert rolled_back_response.status_code == 202, rolled_back_response.text
    rolled_back = _wait_for_deployment(api, rolled_back_response.json()["id"])
    assert rolled_back["status"] == "simulated"
    assert rolled_back["kind"] == "rollback"
    assert rolled_back["previous_deployment_id"] == first["id"]
