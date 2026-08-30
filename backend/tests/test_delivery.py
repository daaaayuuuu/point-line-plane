from __future__ import annotations

import io
import zipfile

from tests.test_deployments import _accept_and_connect, _wait_for_deployment


def _completed_deployment(api, token: str) -> tuple[dict, dict]:
    project, credential = _accept_and_connect(api, token)
    quoted = api.client.post(
        f"/api/v1/projects/{project['id']}/deployment-authorizations",
        json={"credential_id": credential["id"], "action": "deploy"},
    ).json()
    api.client.post(
        f"/api/v1/deployment-authorizations/{quoted['id']}/confirm",
        json={"confirm": True},
    )
    started = api.client.post(
        f"/api/v1/projects/{project['id']}/deployments",
        json={"authorization_id": quoted["id"]},
    )
    assert started.status_code == 202, started.text
    return project, _wait_for_deployment(api, started.json()["id"])


def test_delivery_zip_is_versioned_safe_and_downloadable(api) -> None:
    token, _user = api.login()
    project, deployment = _completed_deployment(api, token)
    created = api.client.post(
        f"/api/v1/projects/{project['id']}/delivery-packages",
        json={"deployment_id": deployment["id"], "confirm": True},
    )
    assert created.status_code == 201, created.text
    package = created.json()
    assert package["status"] == "ready"
    assert package["manifest"]["commit_ref"] == deployment["evidence"]["commit_ref"]
    assert len(package["sha256"]) == 64

    download = api.client.get(package["download_url"])
    assert download.status_code == 200, download.text
    assert download.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        names = set(archive.namelist())
        assert {
            "TECHNICAL_OVERVIEW.md",
            "TEST_REPORT.md",
            "DEPLOYMENT_GUIDE.md",
            "source/app/main.py",
        }.issubset(names)
        assert not any(
            name.endswith((".env", ".db", ".pem", ".key")) or "/.git/" in name
            for name in names
        )

    detail = api.client.get(f"/api/v1/projects/{project['id']}")
    assert detail.status_code == 200
    assert detail.json()["stage"] == "DELIVERY"


def test_github_mock_is_explicit_and_does_not_claim_repository_write(api) -> None:
    token, _user = api.login("GitHub 演练用户", "second-invite")
    project, deployment = _completed_deployment(api, token)
    package = api.client.post(
        f"/api/v1/projects/{project['id']}/delivery-packages",
        json={"deployment_id": deployment["id"], "confirm": True},
    ).json()
    sync = api.client.post(
        f"/api/v1/delivery-packages/{package['id']}/github-sync",
        json={
            "repository_full_name": "example/product-factory-output",
            "branch": "main",
            "confirm": True,
        },
    )
    assert sync.status_code == 202, sync.text
    payload = sync.json()
    assert payload["status"] == "simulated"
    assert payload["repository_url"] is None
    assert payload["evidence"]["repository_modified"] is False
    fetched = api.client.get(f"/api/v1/github-syncs/{payload['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == payload["id"]
