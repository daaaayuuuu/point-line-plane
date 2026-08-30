from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.models import AuditEvent, CredentialRef, UsageLedger
from app.schemas.contracts import AgentResult
from app.services.providers import MockProvider, ProviderCall
from tests.support import assert_error


class _VerifiedProvider:
    name = "openai_compatible"
    model = "verified-test-model"
    verification = "unverified"

    def generate(self, user_input, config):
        return ProviderCall(
            result=AgentResult(
                summary="连接成功",
                key_points=["认证有效"],
                next_step="可以使用",
            ),
            usage={
                "prompt_tokens": 12,
                "completion_tokens": 8,
                "total_tokens": 20,
                "prompt_version": "credential-smoke-v1",
            },
        )


def _connect(api, token: str, key: str = "sk-user-secret-that-must-never-leak") -> dict:
    api.use_token(token)
    response = api.client.post(
        "/api/v1/model-credentials",
        json={
            "provider": "openai_compatible",
            "api_key": key,
            "scope": "both",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_model_key_is_encrypted_masked_and_revoked(api, app, settings) -> None:
    raw_key = "sk-user-secret-that-must-never-leak"
    token, user = api.login("第五阶段凭证用户")
    credential = _connect(api, token, raw_key)
    serialized = str(credential)
    assert raw_key not in serialized
    assert "secret_ref" not in credential
    assert "fingerprint" not in credential
    assert credential["masked_hint"].endswith("leak")
    assert credential["status"] == "unverified"

    secret_files = list(Path(settings.credential_store_root).glob("*.secret"))
    assert len(secret_files) == 1
    assert raw_key not in secret_files[0].read_text(encoding="utf-8")

    with app.state.database.session_factory() as db:
        row = db.scalar(select(CredentialRef).where(CredentialRef.id == credential["id"]))
        assert row is not None
        assert raw_key not in repr(row.__dict__)
        assert app.state.secret_vault.load(owner_id=user["id"], secret_ref=row.secret_ref) == raw_key

    revoked = api.client.post(
        f"/api/v1/model-credentials/{credential['id']}/revoke",
        json={"confirm": True},
    )
    assert revoked.status_code == 200, revoked.text
    assert list(Path(settings.credential_store_root).glob("*.secret")) == []
    listed = api.client.get("/api/v1/model-credentials").json()["items"]
    assert listed[0]["status"] == "revoked"
    with app.state.database.session_factory() as db:
        events = list(
            db.scalars(
                select(AuditEvent).where(
                    AuditEvent.actor_id == user["id"],
                    AuditEvent.action.in_(
                        ["model_credential_connected", "model_credential_revoked"]
                    ),
                )
            )
        )
        assert {item.action for item in events} == {
            "model_credential_connected",
            "model_credential_revoked",
        }


def test_credential_verification_records_usage_without_secret(
    api,
    app,
    monkeypatch,
) -> None:
    token, _user = api.login("第五阶段验证用户")
    credential = _connect(api, token)
    monkeypatch.setattr(
        "app.services.credentials.build_user_provider",
        lambda *args, **kwargs: _VerifiedProvider(),
    )
    rejected = api.client.post(
        f"/api/v1/model-credentials/{credential['id']}/verify",
        json={"confirm_test_charge": False},
    )
    assert_error(rejected, status_code=409, code="COST_CONFIRMATION_REQUIRED")

    verified = api.client.post(
        f"/api/v1/model-credentials/{credential['id']}/verify",
        json={"confirm_test_charge": True},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "verified"
    ledger = api.client.get("/api/v1/usage/ledger")
    assert ledger.status_code == 200, ledger.text
    item = ledger.json()["items"][0]
    assert item["operation"] == "credential_verify"
    assert item["source"] == "user_key"
    assert item["total_tokens"] == 20
    assert "sk-" not in ledger.text
    with app.state.database.session_factory() as db:
        stored = db.scalar(select(UsageLedger).where(UsageLedger.id == item["id"]))
        assert stored is not None
        assert stored.credential_ref_id == credential["id"]


def test_cost_quote_requires_confirmation_and_is_tenant_isolated(api) -> None:
    owner_token, _owner = api.login("第五阶段费用用户")
    credential = _connect(api, owner_token)
    project = api.create_project(owner_token)
    quote = api.client.post(
        f"/api/v1/projects/{project['id']}/cost-quotes",
        json={"operation": "development", "credential_id": credential["id"]},
    )
    assert quote.status_code == 201, quote.text
    payload = quote.json()
    assert payload["source"] == "user_key"
    assert payload["requires_confirmation"] is True
    assert payload["status"] == "pending"
    assert payload["estimated_quota_units"] > 0
    confirmed = api.client.post(
        f"/api/v1/cost-authorizations/{payload['id']}/confirm"
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"
    assert api.client.post(
        f"/api/v1/cost-authorizations/{payload['id']}/confirm"
    ).json()["status"] == "confirmed"

    intruder_token, _intruder = api.login("第五阶段其他用户", "second-invite")
    intruder_project = api.create_project(intruder_token)
    forbidden = api.client.post(
        f"/api/v1/projects/{intruder_project['id']}/cost-quotes",
        json={"operation": "development", "credential_id": credential["id"]},
    )
    assert_error(forbidden, status_code=404, code="NOT_FOUND")


def test_mock_operations_have_usage_evidence_without_spending_quota(api) -> None:
    token, _user = api.login("第五阶段用量用户")
    project, _task, preview_token = api.build_preview(token)
    run = api.client.post(
        f"/api/v1/previews/{preview_token}/runs",
        json={"input": "记录一次可审计的 mock 运行"},
    )
    assert run.status_code == 200, run.text
    ledger = api.client.get(f"/api/v1/usage/ledger?project_id={project['id']}")
    assert ledger.status_code == 200, ledger.text
    assert {item["operation"] for item in ledger.json()["items"]} >= {
        "development",
        "preview_run",
    }
    assert {item["source"] for item in ledger.json()["items"]} == {"mock"}
    quota = api.client.get("/api/v1/usage/quota").json()
    assert quota["remaining_units"] == quota["granted_units"]


def test_verified_user_key_and_confirmed_cost_continue_development(
    api,
    app,
    monkeypatch,
) -> None:
    token, _user = api.login("第五阶段自备 Key 开发用户")
    credential = _connect(api, token)
    with app.state.database.session_factory() as db:
        row = db.get(CredentialRef, credential["id"])
        assert row is not None
        row.status = "verified"
        db.commit()
    monkeypatch.setattr(
        "app.services.credentials.build_user_provider",
        lambda *args, **kwargs: MockProvider("user-key-test-model"),
    )
    project, _prd, _solution = api.prepare_development(token)
    quote = api.client.post(
        f"/api/v1/projects/{project['id']}/cost-quotes",
        json={"operation": "development", "credential_id": credential["id"]},
    ).json()
    confirmed = api.client.post(
        f"/api/v1/cost-authorizations/{quote['id']}/confirm"
    )
    assert confirmed.status_code == 200, confirmed.text
    started = api.client.post(
        f"/api/v1/projects/{project['id']}/development/start",
        json={
            "credential_id": credential["id"],
            "cost_authorization_id": quote["id"],
        },
    )
    assert started.status_code == 200, started.text
    finished = api.wait_for_task(token, started.json()["id"], timeout_seconds=15)
    assert finished["status"] == "succeeded"
    ledger = api.client.get(f"/api/v1/usage/ledger?project_id={project['id']}").json()
    development = next(
        item for item in ledger["items"] if item["operation"] == "development"
    )
    assert development["credential_ref_id"] == credential["id"]
    assert development["source"] == "user_key"


def test_platform_quote_stops_when_free_quota_is_insufficient(settings_factory) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.support import ApiHarness

    settings = settings_factory(ai_provider="openai_compatible", free_quota_units=1)
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        api = ApiHarness(client, settings)
        token, _user = api.login("第五阶段额度耗尽用户")
        project = api.create_project(token)
        response = client.post(
            f"/api/v1/projects/{project['id']}/cost-quotes",
            json={"operation": "development"},
        )
        assert_error(response, status_code=402, code="QUOTA_EXHAUSTED")
