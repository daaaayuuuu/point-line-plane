from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.main import create_app
from tests.support import ApiHarness

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_phase2_schema_is_created_by_alembic(tmp_path: Path, settings_factory) -> None:
    database_path = tmp_path / "phase2-migrated.db"
    database_url = f"sqlite:///{database_path}"
    environment = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": database_url,
        "INVITE_CODES": "phase2-migration-invite",
        "SESSION_SECRET": "phase2-migration-session-secret-not-for-production",
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
        invite_codes="phase2-migration-invite",
    )
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        tables = set(inspect(app.state.database.engine).get_table_names())
        assert {
            "product_graphs",
            "journey_nodes",
            "product_decisions",
            "decision_options",
            "simulation_runs",
            "simulation_steps",
            "friction_findings",
            "product_change_requests",
        }.issubset(tables)

        api = ApiHarness(client, settings)
        token, _user = api.login("迁移用户", "phase2-migration-invite")
        project = api.create_project(token)
        response = client.post(f"/api/v1/projects/{project['id']}/product-graph/initialize")
        assert response.status_code == 200, response.text
        assert len(response.json()["nodes"]) == 5

        with app.state.database.engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("path_separator", "os")
        assert revision == ScriptDirectory.from_config(config).get_current_head()
