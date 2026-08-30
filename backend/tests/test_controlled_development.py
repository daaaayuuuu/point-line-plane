from __future__ import annotations

import json
import subprocess

import pytest
from sqlalchemy import inspect, select

from app.models import CodeVersion, ProductChangeRequest
from app.schemas.contracts import CodingBundle, GeneratedCodeFile
from app.services.development_runtime import ControlledCodingError, validate_bundle
from tests.support import assert_error


def _bundle(*, dangerous_path: str | None = None, secret: str | None = None) -> CodingBundle:
    files = [
        GeneratedCodeFile(
            path=dangerous_path or "README.md",
            language="markdown",
            product_purpose="说明产品",
            content=secret or "# Demo\n",
        ),
        GeneratedCodeFile(
            path="pyproject.toml",
            language="toml",
            product_purpose="依赖",
            content="[project]\nname='demo'\nversion='0.1.0'\n",
        ),
        GeneratedCodeFile(
            path="product_factory.json",
            language="json",
            product_purpose="追溯",
            content='{"template":"demo"}\n',
        ),
        GeneratedCodeFile(
            path="app/main.py",
            language="python",
            product_purpose="入口",
            content="value = 1\n",
        ),
        GeneratedCodeFile(
            path="app/schemas.py",
            language="python",
            product_purpose="结构",
            content="class Input:\n    pass\n",
        ),
        GeneratedCodeFile(
            path="tests/test_contract.py",
            language="python",
            product_purpose="验收契约",
            content="def test_contract():\n    assert True\n",
        ),
    ]
    return CodingBundle(summary="受控代码包", files=files, run_instructions=["后续运行测试"])


def test_phase3_creates_isolated_workspace_tool_evidence_and_readable_files(api) -> None:
    token, _user = api.login("第三阶段用户")
    project, _prd, _solution = api.prepare_development(token)

    missing = api.client.get(
        f"/api/v1/projects/{project['id']}/development-workspace"
    )
    assert_error(missing, status_code=409, code="DEVELOPMENT_WORKSPACE_NOT_READY")

    task = api.start_development(token, project["id"])
    repeated = api.start_development(token, project["id"])
    assert repeated["id"] == task["id"]
    finished = api.wait_for_task(token, task["id"], expected={"succeeded"})
    run_id = finished["checkpoint"]["development_run_id"]

    run_response = api.client.get(f"/api/v1/development-runs/{run_id}")
    assert run_response.status_code == 200, run_response.text
    run = run_response.json()
    assert run["status"] == "succeeded"
    assert run["current_step"] == "preview_ready"
    assert run["provider_verification"] == "mock"
    assert [item["tool_name"] for item in run["tools"]] == [
        "context_loader",
        "coding_provider",
        "workspace_writer",
        "git_checkpoint",
        "quality_runner",
        "preview_runtime",
    ]
    assert all(item["status"] == "succeeded" for item in run["tools"])
    assert {item["path"] for item in run["files"]}.issuperset(
        {"README.md", "pyproject.toml", "product_factory.json", "app/main.py", "web/index.html"}
    )

    workspace = api.client.get(
        f"/api/v1/projects/{project['id']}/development-workspace"
    )
    assert workspace.status_code == 200
    workspace_payload = workspace.json()
    assert workspace_payload["status"] == "ready"
    assert workspace_payload["file_count"] == len(run["files"])
    assert len(workspace_payload["current_commit_ref"]) == 40

    main_file = api.client.get(
        f"/api/v1/code-versions/{run['code_version_id']}/files/app/main.py"
    )
    assert main_file.status_code == 200, main_file.text
    assert "FastAPI" in main_file.json()["content"]
    assert "产品" in main_file.json()["product_purpose"] or "API" in main_file.json()[
        "product_purpose"
    ]


def test_phase3_development_assets_are_tenant_isolated(api) -> None:
    owner_token, _owner = api.login("代码所有者")
    project, _prd, _solution = api.prepare_development(owner_token)
    task = api.start_development(owner_token, project["id"])
    finished = api.wait_for_task(owner_token, task["id"], expected={"succeeded"})
    run_id = finished["checkpoint"]["development_run_id"]
    run = api.client.get(f"/api/v1/development-runs/{run_id}").json()

    intruder_token, _intruder = api.login("其他用户", "second-invite")
    api.use_token(intruder_token)
    assert_error(
        api.client.get(f"/api/v1/development-runs/{run_id}"),
        status_code=404,
        code="NOT_FOUND",
    )
    assert_error(
        api.client.get(
            f"/api/v1/code-versions/{run['code_version_id']}/files/README.md"
        ),
        status_code=404,
        code="NOT_FOUND",
    )


def test_phase3_applies_visual_decisions_and_records_them_in_generated_context(api) -> None:
    token, _user = api.login("产品决策用户")
    project, _prd, _solution = api.prepare_development(token)
    graph = api.client.post(
        f"/api/v1/projects/{project['id']}/product-graph/initialize"
    ).json()
    center = api.client.get(f"/api/v1/projects/{project['id']}/decision-center").json()
    decision = center["items"][0]
    recommended = next(item for item in decision["options"] if item["recommended"])
    confirmed = api.client.post(
        f"/api/v1/decisions/{decision['id']}/confirm",
        json={
            "option_key": recommended["key"],
            "idempotency_key": "phase3-decision-apply-001",
        },
    )
    assert confirmed.status_code == 200, confirmed.text

    api.use_token(token)
    start_response = api.client.post(
        f"/api/v1/projects/{project['id']}/development/start",
        json={"ui_style_key": "ameba-midnight"},
    )
    assert start_response.status_code == 200, start_response.text
    task = start_response.json()
    finished = api.wait_for_task(token, task["id"], expected={"succeeded"})
    assert finished["checkpoint"]["ui_style_key"] == "ameba-midnight"
    run = api.client.get(
        f"/api/v1/development-runs/{finished['checkpoint']['development_run_id']}"
    ).json()
    assert run["context"]["product_context"]["graph_id"] == graph["id"]
    assert run["context"]["product_context"]["ui_style_key"] == "ameba-midnight"
    assert run["context"]["product_context"]["confirmed_decisions"][0][
        "selected_option_key"
    ] == recommended["key"]

    manifest_response = api.client.get(
        f"/api/v1/code-versions/{run['code_version_id']}/files/product_factory.json"
    )
    manifest = json.loads(manifest_response.json()["content"])
    assert manifest["ui_style_key"] == "ameba-midnight"
    assert manifest["product_context"]["confirmed_decisions"][0][
        "selected_option_key"
    ] == recommended["key"]

    with api.client.app.state.database.session_factory() as db:
        change = db.scalar(
            select(ProductChangeRequest).where(
                ProductChangeRequest.project_id == project["id"]
            )
        )
        assert change is not None
        assert change.status == "applied"
        assert change.base_code_version_id == run["code_version_id"]


def test_phase3_in_scope_feedback_creates_a_second_git_commit(api, settings) -> None:
    token, _user = api.login("代码改版用户")
    detail, _task, preview_token = api.build_preview(token)
    first_preview = api.client.get(f"/api/v1/previews/{preview_token}").json()
    first_commit = first_preview["code_version"]["commit_ref"]

    feedback = api.client.post(
        f"/api/v1/projects/{detail['id']}/preview-feedback",
        json={"feedback": "请把结果说明写得更清楚，这是范围内文案调整。"},
    )
    assert feedback.status_code == 200, feedback.text
    second_task = api.start_development(token, detail["id"])
    api.wait_for_task(token, second_task["id"], expected={"succeeded"})
    current = api.client.get(f"/api/v1/projects/{detail['id']}").json()
    second_preview = api.client.get(
        f"/api/v1/previews/{current['preview']['token']}"
    ).json()
    second_commit = second_preview["code_version"]["commit_ref"]
    assert second_commit != first_commit

    repository = settings.workspace_root / detail["id"] / "repository"
    commit_count = subprocess.run(
        ["git", "-C", str(repository), "rev-list", "--count", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert commit_count == "2"


def test_changing_ui_style_after_preview_starts_a_new_build(api) -> None:
    token, _user = api.login("预览换风格用户")
    detail, first_task, _preview_token = api.build_preview(token)
    assert first_task["checkpoint"]["ui_style_key"] == "pirsch-paper"

    api.use_token(token)
    response = api.client.post(
        f"/api/v1/projects/{detail['id']}/development/start",
        json={"ui_style_key": "ameba-midnight"},
    )
    assert response.status_code == 200, response.text
    second_task = response.json()
    assert second_task["id"] != first_task["id"]

    finished = api.wait_for_task(token, second_task["id"], expected={"succeeded"})
    assert finished["checkpoint"]["ui_style_key"] == "ameba-midnight"

    runs = api.client.get(
        f"/api/v1/projects/{detail['id']}/development-runs"
    ).json()["items"]
    assert runs[0]["context"]["product_context"]["ui_style_key"] == "ameba-midnight"

    repeated = api.client.post(
        f"/api/v1/projects/{detail['id']}/development/start",
        json={"ui_style_key": "ameba-midnight"},
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["id"] == second_task["id"]


def test_phase3_code_bundle_rejects_path_escape_secret_and_invalid_python(settings) -> None:
    with pytest.raises(ControlledCodingError) as escaped:
        validate_bundle(_bundle(dangerous_path="../outside.py"), settings)
    assert escaped.value.code == "CODE_PATH_DENIED"

    with pytest.raises(ControlledCodingError) as secret:
        validate_bundle(_bundle(secret="API_KEY='sk-abcdefghijklmnopqrstuvwxyz123456'\n"), settings)
    assert secret.value.code == "SECRET_IN_GENERATED_CODE"

    invalid = _bundle()
    invalid.files[3].content = "def broken(:\n"
    with pytest.raises(ControlledCodingError) as syntax:
        validate_bundle(invalid, settings)
    assert syntax.value.code == "CODE_CONTRACT_INVALID"


def test_phase3_models_are_present_in_isolated_schema(api) -> None:
    tables = set(inspect(api.client.app.state.database.engine).get_table_names())
    assert {
        "development_workspaces",
        "development_runs",
        "tool_executions",
        "code_files",
    }.issubset(tables)
    with api.client.app.state.database.session_factory() as db:
        assert list(db.scalars(select(CodeVersion))) == []
