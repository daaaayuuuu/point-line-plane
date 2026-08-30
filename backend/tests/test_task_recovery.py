from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import Database
from app.main import create_app
from app.models import Task, TaskEvent
from tests.support import ApiHarness


def test_running_task_is_requeued_from_checkpoint_after_app_restart(settings_factory) -> None:
    settings = settings_factory()
    first_app = create_app(settings)
    with TestClient(first_app, raise_server_exceptions=False) as first_client:
        first_api = ApiHarness(first_client, settings)
        token, _user = first_api.login("Recovery User")
        project, _prd, solution = first_api.prepare_development(token)

    database = Database(settings.database_url)
    with database.session_factory() as db:
        interrupted = Task(
            project_id=project["id"],
            idempotency_key=f"development:{project['id']}:1",
            stage="DEVELOPMENT",
            status="running",
            progress=45,
            attempts=1,
            max_attempts=2,
            budget_json={"max_steps": 5, "executor": "controlled_template_only"},
            checkpoint_json={
                "workflow_key": f"development:{project['id']}:1",
                "last_completed_step": "template_generated",
                "solution_artifact_id": solution["id"],
            },
            trace_id="recovery-test-trace",
        )
        db.add(interrupted)
        db.commit()
        task_id = interrupted.id
    database.engine.dispose()

    restarted_app = create_app(settings)
    with TestClient(restarted_app, raise_server_exceptions=False) as restarted_client:
        restarted_api = ApiHarness(restarted_client, settings)
        recovered = restarted_api.wait_for_task(
            token,
            task_id,
            expected={"succeeded"},
            timeout_seconds=15.0,
        )
        # Startup recovery makes the interrupted attempt retryable instead of
        # charging the same in-flight attempt twice against the retry budget.
        assert recovered["attempts"] == 1
        assert recovered["progress"] == 100
        assert recovered["checkpoint"]["last_completed_step"] == "preview_ready"

        with restarted_app.state.database.session_factory() as db:
            events = list(
                db.scalars(
                    select(TaskEvent)
                    .where(TaskEvent.task_id == task_id)
                    .order_by(TaskEvent.sequence)
                )
            )
            assert events[0].type == "retry"
            assert events[0].payload_json["checkpoint"] == "template_generated"
            assert events[-1].type == "done"
            assert [event.sequence for event in events] == list(range(1, len(events) + 1))
            progress_values = [
                event.payload_json["progress"]
                for event in events
                if "progress" in event.payload_json
            ]
            assert progress_values == sorted(progress_values)
            assert min(progress_values) >= 45
            resumed_checkpoints = [
                event.payload_json.get("checkpoint")
                for event in events[1:]
                if event.type == "progress"
            ]
            assert "plan_validated" not in resumed_checkpoints
            assert "template_generated" not in resumed_checkpoints
            assert "contract_validated" in resumed_checkpoints
            assert "schema_tested" not in resumed_checkpoints

        restarted_api.use_token(token)
        project_response = restarted_client.get(f"/api/v1/projects/{project['id']}")
        assert project_response.status_code == 200
        project_detail = project_response.json()
        assert project_detail["stage"] == "PREVIEW_REVIEW"
        assert project_detail["preview"]["code_version"] == 1
