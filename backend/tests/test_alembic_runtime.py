from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.security import secret_hash
from app.main import create_app
from app.models import User
from tests.support import ApiHarness

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_app_uses_alembic_created_schema_when_auto_create_is_disabled(
    tmp_path: Path,
    settings_factory,
) -> None:
    database_path = tmp_path / "alembic-runtime.db"
    database_url = f"sqlite:///{database_path}"
    environment = {
        **os.environ,
        "APP_ENV": "test",
        "DATABASE_URL": database_url,
        "INVITE_CODES": "migration-test-invite",
        "SESSION_SECRET": "migration-test-session-secret-not-for-production",
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
        invite_codes="migration-test-invite",
    )
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        api = ApiHarness(client, settings)
        _token, user = api.login("Migration User", invite_code="migration-test-invite")
        project = api.create_project(_token, name="Migrated Schema Project")
        assert project["name"] == "Migrated Schema Project"
        assert client.get("/api/v1/auth/me").json()["user"]["id"] == user["id"]

        with app.state.database.engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
        alembic_config.set_main_option("path_separator", "os")
        expected_head = ScriptDirectory.from_config(alembic_config).get_current_head()
        assert revision == expected_head

        # The migration must carry the same one-code/one-identity constraint as
        # the ORM metadata; AUTO_CREATE_DB=false means create_all cannot mask it.
        with app.state.database.session_factory() as db:
            db.add(
                User(
                    display_name="Second Identity",
                    invite_code_hash=secret_hash("migration-test-invite"),
                )
            )
            with pytest.raises(IntegrityError):
                db.commit()
