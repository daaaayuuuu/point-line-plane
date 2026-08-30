from __future__ import annotations

from collections.abc import Callable, Iterator
from itertools import count
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.support import ApiHarness


@pytest.fixture
def settings_factory(tmp_path: Path) -> Callable[..., Settings]:
    sequence = count(1)

    def factory(**overrides: Any) -> Settings:
        case = next(sequence)
        values: dict[str, Any] = {
            "app_env": "test",
            "database_url": f"sqlite:///{tmp_path / f'test-{case}.db'}",
            "auto_create_db": True,
            "frontend_origins": "http://testserver",
            "session_cookie_name": "test_product_factory_session",
            "session_ttl_hours": 2,
            "session_secret": "test-session-secret-that-is-never-production",
            "invite_codes": "test-invite,second-invite",
            "ai_provider": "mock",
            "ai_model": "mock-text-agent-test",
            "ai_base_url": "https://example.invalid/v1",
            "ai_api_key": "",
            "ai_timeout_seconds": 0.1,
            "ai_max_attempts": 2,
            "ai_provider_verified": False,
            "workspace_root": tmp_path / f"workspaces-{case}",
            "preview_ttl_hours": 2,
            "max_upload_bytes": 1_024,
            "task_max_attempts": 2,
            "task_force_failure": False,
            "credential_store_root": tmp_path / f"secrets-{case}",
            "credential_master_key": "",
            "free_quota_units": 5_000,
            "deployment_enabled": True,
            "deployment_mode": "mock",
            "deployment_default_region": "cn-beijing",
            "delivery_root": tmp_path / f"deliveries-{case}",
            "backup_root": tmp_path / f"backups-{case}",
            "operations_token": "test-operations-token-not-for-production",
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    return factory


@pytest.fixture
def settings(settings_factory: Callable[..., Settings]) -> Settings:
    return settings_factory()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def api(client: TestClient, settings: Settings) -> ApiHarness:
    return ApiHarness(client=client, settings=settings)
