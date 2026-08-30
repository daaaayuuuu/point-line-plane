from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import CodeVersion, Preview, Project, Task, TaskEvent
from tests.support import ApiHarness, assert_error, sse_event_ids, sse_event_names


def test_development_start_is_idempotent_and_sse_ends_in_done(
    api: ApiHarness,
    client: TestClient,
    app: FastAPI,
) -> None:
    token, _user = api.login("Idempotency User")
    project, _prd, _solution = api.prepare_development(token)

    first = api.start_development(token, project["id"])
    second = api.start_development(token, project["id"])
    assert second["id"] == first["id"]

    finished = api.wait_for_task(token, first["id"], expected={"succeeded"})
    assert finished["progress"] == 100
    assert finished["checkpoint"]["last_completed_step"] == "preview_ready"
    assert finished["error_code"] is None

    third = api.start_development(token, project["id"])
    assert third["id"] == first["id"]

    with app.state.database.session_factory() as db:
        task_count = db.scalar(select(func.count(Task.id)).where(Task.project_id == project["id"]))
        assert task_count == 1
        events = list(
            db.scalars(
                select(TaskEvent)
                .where(TaskEvent.task_id == first["id"])
                .order_by(TaskEvent.sequence)
            )
        )
        assert [event.sequence for event in events] == list(range(1, len(events) + 1))
        assert events[-1].type == "done"
        assert sum(event.type == "done" for event in events) == 1
        assert not any(event.type == "error" for event in events)
        checkpoint_names = {
            event.payload_json.get("checkpoint")
            for event in events
            if event.payload_json.get("checkpoint")
        }
        assert "contract_validated" in checkpoint_names
        assert "schema_tested" not in checkpoint_names

    api.use_token(token)
    stream = client.get(f"/api/v1/tasks/{first['id']}/events")
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    names = sse_event_names(stream.text)
    ids = sse_event_ids(stream.text)
    assert names[-1] == "done"
    assert names.count("done") == 1
    assert ids == sorted(ids)
    assert ids == list(range(1, len(ids) + 1))
    assert '"test_status": "quality_passed"' in stream.text
    assert '"test_status": "passed"' not in stream.text
    assert "schema_tested" not in stream.text
    assert "质量门已通过" in stream.text

    resume_after_terminal = client.get(
        f"/api/v1/tasks/{first['id']}/events",
        headers={"Last-Event-ID": str(ids[-1])},
    )
    assert resume_after_terminal.status_code == 200
    assert sse_event_names(resume_after_terminal.text) == ["done"]


def test_failed_task_retries_to_limit_persists_checkpoint_and_sse_error(
    settings_factory,
) -> None:
    from app.main import create_app

    settings = settings_factory(task_force_failure=True, task_max_attempts=2)
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        api = ApiHarness(client, settings)
        token, _user = api.login("Failure User")
        project, _prd, _solution = api.prepare_development(token)
        task = api.start_development(token, project["id"])
        failed = api.wait_for_task(token, task["id"], expected={"failed"})

        assert failed["attempts"] == 2
        assert failed["max_attempts"] == 2
        assert failed["error_code"] == "CONTROLLED_BUILD_FAILED"
        assert failed["checkpoint"]["last_completed_step"] == "context_loaded"

        detail = client.get(f"/api/v1/projects/{project['id']}")
        assert detail.status_code == 200
        assert detail.json()["stage"] == "PAUSED"
        assert detail.json()["status"] == "PAUSED"
        failure_reports = [
            item for item in detail.json()["latest_artifacts"] if item["type"] == "failure_report"
        ]
        assert len(failure_reports) == 1
        assert failure_reports[0]["content"]["task_id"] == task["id"]

        with app.state.database.session_factory() as db:
            persisted_event_types = list(
                db.scalars(
                    select(TaskEvent.type)
                    .where(TaskEvent.task_id == task["id"])
                    .order_by(TaskEvent.sequence)
                )
            )
        assert "retry" in persisted_event_types
        assert persisted_event_types[-1] == "error"

        stream = client.get(f"/api/v1/tasks/{task['id']}/events")
        assert stream.status_code == 200
        event_names = sse_event_names(stream.text)
        assert "chunk" in event_names
        assert event_names[-1] == "error"
        assert event_names.count("error") == 1
        assert "forced controlled failure" not in stream.text
        assert "traceback" not in stream.text.lower()


def test_failed_task_retry_is_owned_guarded_idempotent_and_can_recover(
    settings_factory,
) -> None:
    from app.main import create_app

    settings = settings_factory(task_force_failure=True, task_max_attempts=1)
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        api = ApiHarness(client, settings)
        owner_token, _owner = api.login("Retry Owner")
        project, _prd, _solution = api.prepare_development(owner_token)
        original = api.start_development(owner_token, project["id"])
        failed = api.wait_for_task(owner_token, original["id"], expected={"failed"})
        assert failed["error_code"] == "CONTROLLED_BUILD_FAILED"

        other_token, _other = api.login("Retry Intruder", invite_code="second-invite")
        api.use_token(other_token)
        denied = client.post(f"/api/v1/tasks/{failed['id']}/retry")
        assert_error(denied, status_code=404, code="NOT_FOUND")

        settings.task_force_failure = False
        api.use_token(owner_token)
        first_retry = client.post(f"/api/v1/tasks/{failed['id']}/retry")
        assert first_retry.status_code == 200, first_retry.text
        retried = first_retry.json()
        assert retried["id"] != failed["id"]
        assert retried["project_id"] == failed["project_id"]

        repeated_retry = client.post(f"/api/v1/tasks/{failed['id']}/retry")
        assert repeated_retry.status_code == 200, repeated_retry.text
        assert repeated_retry.json()["id"] == retried["id"]

        recovered = api.wait_for_task(owner_token, retried["id"], expected={"succeeded"})
        assert recovered["progress"] == 100
        assert recovered["checkpoint"]["last_completed_step"] == "preview_ready"

        with app.state.database.session_factory() as db:
            tasks = list(
                db.scalars(
                    select(Task)
                    .where(Task.project_id == project["id"])
                    .order_by(Task.created_at, Task.id)
                )
            )
            persisted_project = db.get(Project, project["id"])
            assert persisted_project is not None
            assert persisted_project.development_revision == 2
        assert len(tasks) == 2
        assert tasks[0].id == failed["id"]
        assert tasks[1].id == recovered["id"]
        assert tasks[1].idempotency_key == f"retry:{failed['id']}"

        cannot_retry_success = client.post(f"/api/v1/tasks/{recovered['id']}/retry")
        assert_error(
            cannot_retry_success,
            status_code=409,
            code="TASK_NOT_RETRYABLE",
        )


def test_preview_is_bound_to_code_version_runs_are_historic_and_feedback_routes_state(
    api: ApiHarness,
    client: TestClient,
    app: FastAPI,
) -> None:
    token, _user = api.login("Preview User")
    project, first_task, preview_token = api.build_preview(token)

    preview_response = client.get(f"/api/v1/previews/{preview_token}")
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["project_id"] == project["id"]
    assert preview["status"] == "ready"
    assert preview["history"] == []
    assert preview["code_version"]["version"] == 1
    assert preview["code_version"]["test_status"] == "quality_passed"
    assert preview["code_version"]["manifest"]["template"] == "controlled_html_webapp_v1"
    assert preview["code_version"]["manifest"]["project_id"] == project["id"]
    assert first_task["checkpoint"]["code_version_id"] == preview["code_version"]["id"]

    page_response = client.get(preview["url_path"])
    assert page_response.status_code == 200, page_response.text
    assert "text/html" in page_response.headers["content-type"]
    assert 'data-product-preview="controlled-html-webapp-v1"' in page_response.text

    run_response = client.post(
        f"/api/v1/previews/{preview_token}/runs",
        json={"input": "整理这段访谈，指出核心痛点和下一步"},
    )
    assert run_response.status_code == 200, run_response.text
    run = run_response.json()
    assert run["provider"] == "generated_app"
    assert run["model"] == "runtime-provider"
    assert run["provider_verification"] == "mock"
    assert run["usage"]["provider_verification"] == "mock"
    assert run["usage"]["source"] == "generated_runtime"
    assert run["result"]["summary"]
    assert run["result"]["key_points"]
    assert run["result"]["next_step"]

    preview_with_history = client.get(f"/api/v1/previews/{preview_token}")
    assert preview_with_history.status_code == 200
    history = preview_with_history.json()["history"]
    assert len(history) == 1
    assert history[0]["id"] == run["id"]
    assert history[0]["input"] == "整理这段访谈，指出核心痛点和下一步"

    in_scope = client.post(
        f"/api/v1/projects/{project['id']}/preview-feedback",
        json={"feedback": "把摘要语气改得更简洁，并调整结果标题"},
    )
    assert in_scope.status_code == 200, in_scope.text
    assert in_scope.json()["classification"] == "in_scope"
    assert in_scope.json()["next_stage"] == "DEVELOPMENT"
    assert in_scope.json()["solution_artifact"] is None
    change_request = in_scope.json()["change_request_artifact"]
    assert change_request["type"] == "change_request"
    assert change_request["status"] == "confirmed"
    assert (
        change_request["content"]["feedback"]
        == "把摘要语气改得更简洁，并调整结果标题"
    )
    assert change_request["content"]["source_preview_id"] == preview["id"]
    assert (
        change_request["content"]["source_code_version_id"]
        == preview["code_version"]["id"]
    )

    second_task = api.start_development(token, project["id"])
    assert second_task["id"] != first_task["id"]
    completed_second_task = api.wait_for_task(
        token, second_task["id"], expected={"succeeded"}
    )
    assert (
        completed_second_task["checkpoint"]["change_request_artifact_id"]
        == change_request["id"]
    )
    latest_project = client.get(f"/api/v1/projects/{project['id']}").json()
    second_preview_token = latest_project["preview"]["token"]
    assert second_preview_token != preview_token
    second_preview = client.get(f"/api/v1/previews/{second_preview_token}").json()
    assert second_preview["code_version"]["version"] == 2
    second_manifest = second_preview["code_version"]["manifest"]
    assert second_manifest["change_request_artifact_id"] == change_request["id"]
    assert second_manifest["change_request"]["feedback"] == change_request["content"]["feedback"]

    new_scope = client.post(
        f"/api/v1/projects/{project['id']}/preview-feedback",
        json={"feedback": "新增文件上传和知识库检索"},
    )
    assert new_scope.status_code == 200, new_scope.text
    assert new_scope.json()["classification"] == "new_scope"
    assert new_scope.json()["next_stage"] == "SOLUTION_REVIEW"
    revised_solution = new_scope.json()["solution_artifact"]
    assert revised_solution["version"] == 2
    assert revised_solution["status"] == "draft"
    assert "预览反馈" in revised_solution["content"]["revision_notes"][-1]

    with app.state.database.session_factory() as db:
        code_versions = list(
            db.scalars(
                select(CodeVersion)
                .where(CodeVersion.project_id == project["id"])
                .order_by(CodeVersion.version)
            )
        )
        previews = list(
            db.scalars(
                select(Preview)
                .where(Preview.project_id == project["id"])
                .order_by(Preview.created_at)
            )
        )
        assert [item.version for item in code_versions] == [1, 2]
        assert {item.test_status for item in code_versions} == {"quality_passed"}
        assert all(item.test_status != "passed" for item in code_versions)
        assert [item.code_version_id for item in previews] == [item.id for item in code_versions]
