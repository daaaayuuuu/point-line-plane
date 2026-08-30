from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import Artifact, Project, RequirementSession
from tests.support import ApiHarness, assert_error


def test_workflow_gates_reject_skipped_confirmations(
    api: ApiHarness,
    client: TestClient,
) -> None:
    token, _user = api.login("Workflow User")
    project = api.create_project(token)
    project_id = project["id"]
    assert project["stage"] == "REQUIREMENTS"

    before_prd = client.post(f"/api/v1/projects/{project_id}/development/start")
    assert_error(before_prd, status_code=409, code="INVALID_PROJECT_STAGE")

    prd = api.create_prd(token, project_id)
    assert prd["type"] == "prd"
    assert prd["status"] == "draft"

    before_prd_confirmation = client.post(f"/api/v1/projects/{project_id}/development/start")
    assert_error(before_prd_confirmation, status_code=409, code="INVALID_PROJECT_STAGE")

    wrong_confirmation_endpoint = client.post(
        f"/api/v1/projects/{project_id}/confirmations/solution",
        json={"artifact_id": prd["id"], "decision": "confirm"},
    )
    assert_error(wrong_confirmation_endpoint, status_code=400, code="ARTIFACT_MISMATCH")

    prd_confirmation = client.post(
        f"/api/v1/projects/{project_id}/confirmations/prd",
        json={"artifact_id": prd["id"], "decision": "confirm"},
    )
    assert prd_confirmation.status_code == 200
    solution = prd_confirmation.json()["next_artifact"]
    assert prd_confirmation.json()["project"]["stage"] == "SOLUTION_REVIEW"

    before_solution_confirmation = client.post(f"/api/v1/projects/{project_id}/development/start")
    assert_error(before_solution_confirmation, status_code=409, code="INVALID_PROJECT_STAGE")

    further_requirements = client.post(
        f"/api/v1/projects/{project_id}/requirements/messages",
        json={"message": "试图跳回需求阶段"},
    )
    assert_error(further_requirements, status_code=409, code="INVALID_PROJECT_STAGE")

    solution_confirmation = client.post(
        f"/api/v1/projects/{project_id}/confirmations/solution",
        json={"artifact_id": solution["id"], "decision": "confirm"},
    )
    assert solution_confirmation.status_code == 200
    assert solution_confirmation.json()["project"]["stage"] == "DEVELOPMENT"


def test_first_requirement_answer_creates_prd(
    api: ApiHarness,
    client: TestClient,
) -> None:
    token, _user = api.login("Requirement Rounds User")
    project = api.create_project(token)
    project_id = project["id"]
    assert project["next_action"]["code"] == "answer_requirements"
    assert [item["id"] for item in project["next_action"]["questions"]] == ["target_user"]

    final = client.post(
        f"/api/v1/projects/{project_id}/requirements/messages",
        json={
            "message": "独立产品经理，他们没有工程团队，需要直接获得可执行的结构化建议。",
            "question_id": "target_user",
        },
    )
    assert final.status_code == 200, final.text
    payload = final.json()
    assert payload["status"] == "prd_ready"
    assert payload["questions"] == []
    assert payload["artifact"]["type"] == "prd"
    assert payload["artifact"]["version"] == 1
    assert payload["project"]["stage"] == "PRD_REVIEW"


def test_concurrent_answers_for_the_same_question_advance_exactly_once(
    api: ApiHarness,
    client: TestClient,
    app: FastAPI,
    settings,
) -> None:
    token, _user = api.login("Concurrent Requirement User")
    project = api.create_project(token, name="Concurrent Requirements")
    project_id = project["id"]
    question_id = project["next_action"]["questions"][0]["id"]
    assert question_id == "target_user"

    barrier = Barrier(2)
    cookie_header = f"{settings.session_cookie_name}={token}"
    messages = ["并发回答 A：独立产品经理", "并发回答 B：小型创业团队"]
    concurrent_clients = [
        TestClient(app, raise_server_exceptions=False),
        TestClient(app, raise_server_exceptions=False),
    ]

    def submit(index: int):
        barrier.wait(timeout=5)
        return concurrent_clients[index].post(
            f"/api/v1/projects/{project_id}/requirements/messages",
            json={"message": messages[index], "question_id": question_id},
            headers={"Cookie": cookie_header},
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(submit, range(2)))
    finally:
        for concurrent_client in concurrent_clients:
            concurrent_client.close()

    assert sorted(response.status_code for response in responses) == [200, 409]
    successful_index = next(
        index for index, response in enumerate(responses) if response.status_code == 200
    )
    successful = responses[successful_index].json()
    assert successful["status"] == "prd_ready"
    assert successful["artifact"]["type"] == "prd"
    assert successful["project"]["stage"] == "PRD_REVIEW"
    assert successful["questions"] == []

    conflict = next(response for response in responses if response.status_code == 409)
    assert_error(conflict, status_code=409, code="STALE_REQUIREMENT_QUESTION")

    with app.state.database.session_factory() as db:
        requirement = db.scalar(
            select(RequirementSession).where(RequirementSession.project_id == project_id)
        )
        persisted_project = db.get(Project, project_id)
        artifact_count = db.scalar(
            select(func.count(Artifact.id)).where(Artifact.project_id == project_id)
        )
        assert requirement is not None
        business_answers = [
            item
            for item in requirement.answers_json["messages"]
            if item.get("kind") != "idea"
        ]
        assert requirement.round == 1
        assert requirement.missing_items_json == []
        assert len(business_answers) == 1
        assert business_answers[0]["content"] == messages[successful_index]
        assert business_answers[0]["question_id"] == "target_user"
        assert persisted_project is not None
        assert persisted_project.stage == "PRD_REVIEW"
        assert artifact_count == 1


def test_prd_and_solution_revisions_are_versioned_and_stale_versions_are_rejected(
    api: ApiHarness,
    client: TestClient,
) -> None:
    token, _user = api.login("Version User")
    project = api.create_project(token)
    project_id = project["id"]
    prd_v1 = api.create_prd(token, project_id, message="第一版补充信息")
    assert prd_v1["version"] == 1

    requirement_revision = client.post(
        f"/api/v1/projects/{project_id}/requirements/messages",
        json={"message": "第二版补充：结果要方便复制"},
    )
    assert requirement_revision.status_code == 200
    prd_v2 = requirement_revision.json()["artifact"]
    assert prd_v2["version"] == 2

    stale = client.post(
        f"/api/v1/projects/{project_id}/confirmations/prd",
        json={"artifact_id": prd_v1["id"], "decision": "confirm"},
    )
    assert_error(stale, status_code=409, code="STALE_ARTIFACT")

    explicit_revision = client.post(
        f"/api/v1/projects/{project_id}/confirmations/prd",
        json={
            "artifact_id": prd_v2["id"],
            "decision": "revise",
            "comment": "请把验收标准写得更具体",
        },
    )
    assert explicit_revision.status_code == 200
    prd_revision_confirmation = explicit_revision.json()["confirmation"]
    assert prd_revision_confirmation["decision"] == "revise"
    assert prd_revision_confirmation["comment"] == "请把验收标准写得更具体"
    prd_v3 = explicit_revision.json()["next_artifact"]
    assert prd_v3["version"] == 3
    assert prd_v3["status"] == "draft"
    assert prd_v3["content"]["revision_notes"][-1] == "请把验收标准写得更具体"

    prd_items_response = client.get(f"/api/v1/projects/{project_id}/artifacts?type=prd")
    assert prd_items_response.status_code == 200
    prd_items = prd_items_response.json()["items"]
    assert [item["version"] for item in prd_items] == [3, 2, 1]
    assert [item["status"] for item in prd_items] == ["draft", "superseded", "superseded"]

    confirm_prd = client.post(
        f"/api/v1/projects/{project_id}/confirmations/prd",
        json={"artifact_id": prd_v3["id"], "decision": "confirm"},
    )
    assert confirm_prd.status_code == 200
    first_prd_confirmation = confirm_prd.json()["confirmation"]
    solution_v1 = confirm_prd.json()["next_artifact"]
    assert solution_v1["version"] == 1

    repeat_prd_confirmation = client.post(
        f"/api/v1/projects/{project_id}/confirmations/prd",
        json={"artifact_id": prd_v3["id"], "decision": "confirm"},
    )
    assert repeat_prd_confirmation.status_code == 200
    assert repeat_prd_confirmation.json()["confirmation"]["id"] == first_prd_confirmation["id"]
    assert repeat_prd_confirmation.json()["next_artifact"]["id"] == solution_v1["id"]

    revise_solution = client.post(
        f"/api/v1/projects/{project_id}/confirmations/solution",
        json={
            "artifact_id": solution_v1["id"],
            "decision": "revise",
            "comment": "降低首版外部账号依赖",
        },
    )
    assert revise_solution.status_code == 200
    assert revise_solution.json()["confirmation"]["decision"] == "revise"
    solution_v2 = revise_solution.json()["next_artifact"]
    assert solution_v2["version"] == 2
    assert solution_v2["content"]["revision_notes"][-1] == "降低首版外部账号依赖"

    confirm_solution = client.post(
        f"/api/v1/projects/{project_id}/confirmations/solution",
        json={"artifact_id": solution_v2["id"], "decision": "confirm"},
    )
    assert confirm_solution.status_code == 200
    first_solution_confirmation = confirm_solution.json()["confirmation"]
    assert confirm_solution.json()["project"]["stage"] == "DEVELOPMENT"

    repeat_solution_confirmation = client.post(
        f"/api/v1/projects/{project_id}/confirmations/solution",
        json={"artifact_id": solution_v2["id"], "decision": "confirm"},
    )
    assert repeat_solution_confirmation.status_code == 200
    assert repeat_solution_confirmation.json()["confirmation"]["id"] == first_solution_confirmation["id"]

    detail = client.get(f"/api/v1/projects/{project_id}")
    assert detail.status_code == 200
    assert len(detail.json()["confirmations"]) == 4


def test_revision_requires_a_comment_and_artifact_filter_is_validated(
    api: ApiHarness,
    client: TestClient,
) -> None:
    token, _user = api.login("Validation User")
    project = api.create_project(token)
    prd = api.create_prd(token, project["id"])

    no_comment = client.post(
        f"/api/v1/projects/{project['id']}/confirmations/prd",
        json={"artifact_id": prd["id"], "decision": "revise"},
    )
    assert_error(no_comment, status_code=422, code="VALIDATION_ERROR")

    bad_filter = client.get(f"/api/v1/projects/{project['id']}/artifacts?type=secret")
    assert_error(bad_filter, status_code=422, code="INVALID_ARTIFACT_TYPE")
