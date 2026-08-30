from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.main import create_app
from tests.support import ApiHarness

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_phase3_schema_and_development_run_work_on_alembic_database(
    tmp_path: Path,
    settings_factory,
) -> None:
    database_path = tmp_path / "phase3-migrated.db"
    database_url = f"sqlite:///{database_path}"
    environment = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": database_url,
        "INVITE_CODES": "phase3-migration-invite",
        "SESSION_SECRET": "phase3-migration-session-secret-not-for-production",
        "AI_PROVIDER": "mock",
    }
    migrated = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(BACKEND_ROOT / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr

    settings = settings_factory(
        database_url=database_url,
        auto_create_db=False,
        invite_codes="phase3-migration-invite",
        workspace_root=tmp_path / "phase3-workspaces",
    )
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        tables = set(inspect(app.state.database.engine).get_table_names())
        assert {
            "development_workspaces",
            "development_runs",
            "tool_executions",
            "code_files",
            "quality_runs",
            "repair_attempts",
            "preview_runtimes",
        }.issubset(tables)

        api = ApiHarness(client, settings)
        token, _user = api.login("第三阶段迁移用户", "phase3-migration-invite")
        project, _prd, _solution = api.prepare_development(token)
        task = api.start_development(token, project["id"])
        finished = api.wait_for_task(token, task["id"], expected={"succeeded"})
        run = client.get(
            f"/api/v1/development-runs/{finished['checkpoint']['development_run_id']}"
        )
        assert run.status_code == 200, run.text
        assert run.json()["files"]

        with app.state.database.engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "20260821_0008"
