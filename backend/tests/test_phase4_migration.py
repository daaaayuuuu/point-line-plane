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


def test_phase4_migration_builds_quality_schema_and_runs_full_flow(
    tmp_path: Path,
    settings_factory,
) -> None:
    database_path = tmp_path / "phase4-migrated.db"
    database_url = f"sqlite:///{database_path}"
    environment = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": database_url,
        "INVITE_CODES": "phase4-migration-invite",
        "SESSION_SECRET": "phase4-migration-session-secret-not-for-production",
        "AI_PROVIDER": "mock",
    }
    migrated = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(BACKEND_ROOT / "alembic.ini"), "upgrade", "head"],
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
        invite_codes="phase4-migration-invite",
        workspace_root=tmp_path / "phase4-workspaces",
    )
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert {
            "quality_runs",
            "repair_attempts",
            "preview_runtimes",
        }.issubset(set(inspect(app.state.database.engine).get_table_names()))
        api = ApiHarness(client, settings)
        token, _user = api.login("第四阶段迁移用户", "phase4-migration-invite")
        project, _task, preview_token = api.build_preview(token)
        assert client.get(f"/api/v1/projects/{project['id']}/quality-history").status_code == 200
        assert client.get(f"/api/v1/previews/{preview_token}/runtime").status_code == 200
        with app.state.database.engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "20260821_0008"
