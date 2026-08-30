from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_phase8_migration_and_readiness_probe(tmp_path: Path, settings_factory) -> None:
    database_url = f"sqlite:///{tmp_path / 'phase8-migrated.db'}"
    environment = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": database_url,
        "INVITE_CODES": "phase8-migration-invite",
        "SESSION_SECRET": "phase8-migration-session-secret-not-production",
        "CREDENTIAL_STORE_ROOT": str(tmp_path / "secrets"),
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
        invite_codes="phase8-migration-invite",
        backup_root=tmp_path / "backups",
    )
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert {"beta_invites", "rate_limit_events", "backup_records"}.issubset(
            set(inspect(app.state.database.engine).get_table_names())
        )
        ready = client.get("/api/v1/health/ready")
        assert ready.status_code == 200, ready.text
        assert ready.json() == {"status": "ready", "migration": "20260821_0008"}
        with app.state.database.engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260821_0008"
