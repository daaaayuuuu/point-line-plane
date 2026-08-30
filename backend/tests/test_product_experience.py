from __future__ import annotations

from typing import Any

from tests.support import assert_error


def _initialize(api, token: str, project_id: str) -> dict[str, Any]:
    api.use_token(token)
    response = api.client.post(f"/api/v1/projects/{project_id}/product-graph/initialize")
    assert response.status_code == 200, response.text
    return response.json()


def test_product_graph_is_explicit_idempotent_and_dual_language(api) -> None:
    token, _user = api.login()
    project = api.create_project(token, name="面试复盘助手", idea="把复盘变成薄弱点和练习题")

    missing = api.client.get(f"/api/v1/projects/{project['id']}/product-graph")
    assert_error(missing, status_code=409, code="PRODUCT_GRAPH_NOT_INITIALIZED")

    graph = _initialize(api, token, project["id"])
    repeated = _initialize(api, token, project["id"])
    assert repeated["id"] == graph["id"]
    assert graph["version"] == 1
    assert [node["key"] for node in graph["nodes"]] == [
        "target_user",
        "input",
        "ai_analysis",
        "result",
        "history",
    ]

    input_node = graph["nodes"][1]
    assert "用户" in input_node["product_purpose"]
    assert input_node["technical_contract"]["request_schema"] == "PreviewRunRequest"
    assert (
        input_node["technical_contract"]["api"]
        == "POST /api/v1/previews/{preview_token}/runs"
    )

    center_response = api.client.get(f"/api/v1/projects/{project['id']}/decision-center")
    assert center_response.status_code == 200, center_response.text
    center = center_response.json()
    assert center["open_count"] == 2
    assert center["confirmed_count"] == 0
    assert any(option["recommended"] for option in center["items"][0]["options"])
    assert center["items"][0]["options"][0]["technical_effects"]["api_contract"]


def test_product_experience_preserves_tenant_boundary(api) -> None:
    first_token, _first = api.login("第一位用户", "test-invite")
    first_project = api.create_project(first_token)
    graph = _initialize(api, first_token, first_project["id"])

    second_token, _second = api.login("第二位用户", "second-invite")
    api.use_token(second_token)
    assert_error(
        api.client.get(f"/api/v1/projects/{first_project['id']}/product-graph"),
        status_code=404,
        code="NOT_FOUND",
    )
    assert_error(
        api.client.post(
            f"/api/v1/product-graphs/{graph['id']}/simulations",
            json={
                "persona_key": "first_time_non_technical_user",
                "idempotency_key": "tenant-boundary-001",
            },
        ),
        status_code=404,
        code="NOT_FOUND",
    )


def test_decision_confirmation_records_product_and_technical_impact(api) -> None:
    token, _user = api.login()
    project = api.create_project(token)
    graph = _initialize(api, token, project["id"])
    center = api.client.get(f"/api/v1/projects/{project['id']}/decision-center").json()
    decision = center["items"][0]
    recommended = next(option for option in decision["options"] if option["recommended"])
    body = {"option_key": recommended["key"], "idempotency_key": "decision-confirm-001"}

    first = api.client.post(f"/api/v1/decisions/{decision['id']}/confirm", json=body)
    assert first.status_code == 200, first.text
    repeated = api.client.post(f"/api/v1/decisions/{decision['id']}/confirm", json=body)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["change_request"]["id"] == first.json()["change_request"]["id"]

    payload = first.json()
    assert payload["decision"]["status"] == "confirmed"
    assert payload["change_request"]["scope_classification"] == "in_scope"
    assert payload["change_request"]["product_impact"]["learning_cost"] == "low"
    assert payload["change_request"]["technical_context"]["frontend_component"] == "InputPanel"
    assert payload["change_request"]["graph_id"] == graph["id"]

    conflict = api.client.post(
        f"/api/v1/decisions/{decision['id']}/confirm",
        json={
            "option_key": decision["options"][-1]["key"],
            "idempotency_key": "decision-confirm-002",
        },
    )
    assert_error(conflict, status_code=409, code="DECISION_ALREADY_CONFIRMED")


def test_virtual_user_walkthrough_finds_repairs_and_recovers_friction(api) -> None:
    token, _user = api.login()
    project = api.create_project(token, name="面试复盘助手")
    graph = _initialize(api, token, project["id"])
    start_body = {
        "persona_key": "first_time_non_technical_user",
        "idempotency_key": "walkthrough-run-001",
    }
    started = api.client.post(
        f"/api/v1/product-graphs/{graph['id']}/simulations",
        json=start_body,
    )
    assert started.status_code == 200, started.text
    repeated = api.client.post(
        f"/api/v1/product-graphs/{graph['id']}/simulations",
        json=start_body,
    )
    assert repeated.status_code == 200, repeated.text
    run_id = started.json()["id"]
    assert repeated.json()["id"] == run_id

    first_step = api.client.post(f"/api/v1/simulations/{run_id}/advance")
    assert first_step.status_code == 200, first_step.text
    assert first_step.json()["steps"][-1]["node_key"] == "target_user"
    assert first_step.json()["steps"][-1]["status"] == "passed"

    blocked = api.client.post(f"/api/v1/simulations/{run_id}/advance")
    assert blocked.status_code == 200, blocked.text
    blocked_payload = blocked.json()
    assert blocked_payload["status"] == "blocked"
    assert blocked_payload["steps"][-1]["node_key"] == "input"
    assert blocked_payload["steps"][-1]["status"] == "blocked"
    finding = blocked_payload["findings"][0]
    assert finding["severity"] == "blocker"
    assert finding["evidence"]["technical_check"] == "input_guidance_present=false"
    assert any(option["recommended"] for option in finding["resolution_options"])

    assert_error(
        api.client.post(f"/api/v1/simulations/{run_id}/advance"),
        status_code=409,
        code="SIMULATION_BLOCKED",
    )

    resolution_body = {
        "resolution_key": "add_input_example",
        "idempotency_key": "finding-resolution-001",
    }
    resolved = api.client.post(
        f"/api/v1/findings/{finding['id']}/resolve",
        json=resolution_body,
    )
    assert resolved.status_code == 200, resolved.text
    resolved_again = api.client.post(
        f"/api/v1/findings/{finding['id']}/resolve",
        json=resolution_body,
    )
    assert resolved_again.status_code == 200, resolved_again.text
    assert (
        resolved_again.json()["change_request"]["id"]
        == resolved.json()["change_request"]["id"]
    )
    assert resolved.json()["finding"]["status"] == "resolved"
    assert resolved.json()["change_request"]["technical_context"]["api_contract"] == "unchanged"

    final_payload: dict[str, Any] | None = None
    for _ in range(8):
        response = api.client.post(f"/api/v1/simulations/{run_id}/advance")
        assert response.status_code == 200, response.text
        final_payload = response.json()
        if final_payload["status"] == "succeeded":
            break
    assert final_payload is not None
    assert final_payload["status"] == "succeeded"
    assert final_payload["checkpoint"]["completed_node_keys"] == [
        "target_user",
        "input",
        "ai_analysis",
        "result",
        "history",
    ]

    persisted = api.client.get(f"/api/v1/simulations/{run_id}")
    assert persisted.status_code == 200, persisted.text
    assert persisted.json()["status"] == "succeeded"
    assert len(persisted.json()["steps"]) == 6

    dashboard = api.client.get(f"/api/v1/projects/{project['id']}/product-dashboard")
    assert dashboard.status_code == 200, dashboard.text
    dashboard_payload = dashboard.json()
    assert dashboard_payload["latest_simulation"]["id"] == run_id
    assert dashboard_payload["open_findings"] == []
    assert any(
        change["source_type"] == "simulation"
        for change in dashboard_payload["queued_changes"]
    )


def test_dashboard_prioritizes_blocker_over_open_decisions(api) -> None:
    token, _user = api.login()
    project = api.create_project(token)
    graph = _initialize(api, token, project["id"])
    started = api.client.post(
        f"/api/v1/product-graphs/{graph['id']}/simulations",
        json={
            "persona_key": "first_time_non_technical_user",
            "idempotency_key": "dashboard-blocker-001",
        },
    ).json()
    api.client.post(f"/api/v1/simulations/{started['id']}/advance")
    api.client.post(f"/api/v1/simulations/{started['id']}/advance")

    dashboard = api.client.get(f"/api/v1/projects/{project['id']}/product-dashboard")
    assert dashboard.status_code == 200, dashboard.text
    payload = dashboard.json()
    assert payload["decision_center"]["open_count"] == 2
    assert payload["next_action"]["code"] == "resolve_friction"
    assert len(payload["open_findings"]) == 1
