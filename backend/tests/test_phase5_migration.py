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


def test_phase5_migration_builds_credentials_usage_schema(
    tmp_path: Path,
    settings_factory,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'phase5-migrated.db'}"
    environment = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": database_url,
        "INVITE_CODES": "phase5-migration-invite",
        "SESSION_SECRET": "phase5-migration-session-secret-not-for-production",
        "AI_PROVIDER": "mock",
        "CREDENTIAL_STORE_ROOT": str(tmp_path / "migration-secrets"),
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
        invite_codes="phase5-migration-invite",
        credential_store_root=tmp_path / "migration-secrets",
    )
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        tables = set(inspect(app.state.database.engine).get_table_names())
        assert {
            "credential_refs",
            "quota_accounts",
            "usage_ledgers",
            "cost_authorizations",
        }.issubset(tables)
        api = ApiHarness(client, settings)
        token, _user = api.login("第五阶段迁移用户", "phase5-migration-invite")
        project = api.create_project(token)
        connected = client.post(
            "/api/v1/model-credentials",
            json={
                "provider": "openai_compatible",
                "api_key": "sk-phase5-migration-secret",
                "scope": "development",
                "project_id": project["id"],
            },
        )
        assert connected.status_code == 201, connected.text
        assert client.get("/api/v1/usage/quota").status_code == 200
        with app.state.database.engine.connect() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "20260821_0008"
