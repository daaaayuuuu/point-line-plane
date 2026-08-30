from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import CodeVersion, DevelopmentWorkspace, RepairAttempt
from app.services.quality_runtime import QualityRuntimeError, run_quality_command
from tests.support import ApiHarness, assert_error


def test_quality_gate_runs_real_commands_and_generated_runtime_api(api, app) -> None:
    token, _user = api.login("第四阶段质量用户")
    project, task, preview_token = api.build_preview(token)

    assert task["checkpoint"]["last_completed_step"] == "preview_ready"
    history_response = api.client.get(
        f"/api/v1/projects/{project['id']}/quality-history"
    )
    assert history_response.status_code == 200, history_response.text
    history = history_response.json()
    assert [item["kind"] for item in history["quality_runs"]] == [
        "compile",
        "pytest",
        "runtime_smoke",
    ]
    assert {item["status"] for item in history["quality_runs"]} == {"passed"}
    assert history["repair_attempts"] == []
    assert all("sk-" not in item["output_excerpt"] for item in history["quality_runs"])

    runtime_response = api.client.get(f"/api/v1/previews/{preview_token}/runtime")
    assert runtime_response.status_code == 200, runtime_response.text
    runtime = runtime_response.json()
    assert runtime["status"] == "ready"
    assert runtime["base_url"] == f"/api/v1/previews/{preview_token}/runtime"
    assert "127.0.0.1" not in runtime["base_url"]

    analyzed = api.client.post(
        f"/api/v1/previews/{preview_token}/runtime/analyze",
        json={"input": "请整理这次真实的产品访谈"},
    )
    assert analyzed.status_code == 200, analyzed.text
    assert analyzed.json()["result"]["summary"]
    assert analyzed.json()["history_count"] >= 2

    generated_history = api.client.get(
        f"/api/v1/previews/{preview_token}/runtime/history"
    )
    assert generated_history.status_code == 200, generated_history.text
    assert len(generated_history.json()["items"]) >= 2

    with app.state.database.session_factory() as db:
        versions = list(
            db.scalars(
                select(CodeVersion).where(CodeVersion.project_id == project["id"])
            )
        )
        assert len(versions) == 1
        assert versions[0].test_status == "quality_passed"
        assert versions[0].manifest_json["quality_gate"]["status"] == "passed"


def test_quality_failure_triggers_one_repair_and_new_git_version(settings_factory) -> None:
    settings = settings_factory(quality_force_failures=1, quality_max_repairs=2)
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        api = ApiHarness(client, settings)
        token, _user = api.login("第四阶段修复用户")
        project, task, preview_token = api.build_preview(token)
        assert task["status"] == "succeeded"
        assert client.get(f"/api/v1/previews/{preview_token}/runtime").status_code == 200

        history = client.get(
            f"/api/v1/projects/{project['id']}/quality-history"
        ).json()
        assert [item["status"] for item in history["repair_attempts"]] == ["succeeded"]
        assert history["repair_attempts"][0]["source_code_version_id"]
        assert history["repair_attempts"][0]["repaired_code_version_id"]
        assert any(
            item["kind"] == "pytest" and item["status"] == "failed"
            for item in history["quality_runs"]
        )
        assert history["quality_runs"][-1]["kind"] == "runtime_smoke"
        assert history["quality_runs"][-1]["status"] == "passed"

        with app.state.database.session_factory() as db:
            versions = list(
                db.scalars(
                    select(CodeVersion)
                    .where(CodeVersion.project_id == project["id"])
                    .order_by(CodeVersion.version)
                )
            )
            assert [item.version for item in versions] == [1, 2]
            assert [item.test_status for item in versions] == [
                "quality_failed",
                "quality_passed",
            ]
            assert versions[0].commit_ref != versions[1].commit_ref


def test_exhausted_repairs_pause_and_restore_last_good_commit(settings_factory) -> None:
    settings = settings_factory(quality_max_repairs=1, quality_force_failures=0)
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        api = ApiHarness(client, settings)
        token, _user = api.login("第四阶段回退用户")
        project, _first_task, first_preview_token = api.build_preview(token)
        first_preview = client.get(f"/api/v1/previews/{first_preview_token}").json()
        first_version = first_preview["code_version"]

        feedback = client.post(
            f"/api/v1/projects/{project['id']}/preview-feedback",
            json={"feedback": "把结果摘要改得更简洁"},
        )
        assert feedback.status_code == 200, feedback.text
        assert feedback.json()["classification"] == "in_scope"

        settings.quality_force_failures = 3
        second_task = api.start_development(token, project["id"])
        failed = api.wait_for_task(token, second_task["id"], expected={"failed"})
        assert failed["error_code"] == "QUALITY_GATE_FAILED"
        assert failed["checkpoint"]["rolled_back_to_code_version_id"] == first_version["id"]

        detail = client.get(f"/api/v1/projects/{project['id']}").json()
        assert detail["stage"] == "PAUSED"
        with app.state.database.session_factory() as db:
            workspace = db.scalar(
                select(DevelopmentWorkspace).where(
                    DevelopmentWorkspace.project_id == project["id"]
                )
            )
            assert workspace is not None
            assert workspace.current_commit_ref == first_version["commit_ref"]
            repairs = list(
                db.scalars(
                    select(RepairAttempt).where(RepairAttempt.task_id == second_task["id"])
                )
            )
            assert len(repairs) == 1


def test_runtime_recovers_after_backend_restart(settings_factory) -> None:
    settings = settings_factory()
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as first_client:
        api = ApiHarness(first_client, settings)
        token, _user = api.login("第四阶段恢复用户")
        project, _task, preview_token = api.build_preview(token)
        assert first_client.get(f"/api/v1/previews/{preview_token}/runtime").status_code == 200

    recovered_app = create_app(settings)
    with TestClient(recovered_app, raise_server_exceptions=False) as recovered_client:
        recovered_api = ApiHarness(recovered_client, settings)
        recovered_token, _user = recovered_api.login("第四阶段恢复用户")
        recovered_api.use_token(recovered_token)
        recovered = recovered_client.get(f"/api/v1/previews/{preview_token}/runtime")
        assert recovered.status_code == 200, recovered.text
        assert recovered.json()["status"] == "ready"
        detail = recovered_client.get(f"/api/v1/projects/{project['id']}")
        assert detail.status_code == 200
        assert detail.json()["preview"]["token"] == preview_token


def test_quality_history_is_tenant_isolated(api) -> None:
    owner_token, _owner = api.login("第四阶段所有者")
    project, _task, _preview_token = api.build_preview(owner_token)
    intruder_token, _intruder = api.login("第四阶段其他用户", "second-invite")
    api.use_token(intruder_token)
    assert_error(
        api.client.get(f"/api/v1/projects/{project['id']}/quality-history"),
        status_code=404,
        code="NOT_FOUND",
    )


def test_real_provider_code_is_rejected_without_external_sandbox(settings_factory, tmp_path) -> None:
    settings = settings_factory(workspace_root=tmp_path / "workspaces")
    try:
        run_quality_command(
            settings=settings,
            project_id="00000000-0000-0000-0000-000000000000",
            provider="openai_compatible",
            kind="pytest",
        )
    except QualityRuntimeError as exc:
        assert exc.code == "EXTERNAL_SANDBOX_REQUIRED"
    else:
        raise AssertionError("real-provider code must not run in the trusted mock executor")
