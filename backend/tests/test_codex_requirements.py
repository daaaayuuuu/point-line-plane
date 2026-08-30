from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.schemas.contracts import PrdContent
from app.services.codex_auth import CodexTurnResult
from app.services.codex_requirements import CodexRequirementDecisionOutput, CodexRequirementOutput
from tests.support import ApiHarness


class FakeCodexConversationBridge:
    def __init__(self) -> None:
        self.turns = 0
        self.resumed: list[str] = []
        self.started_instructions: list[str] = []
        self.messages: list[str] = []

    def start_thread(self, *, cwd: Path, developer_instructions: str) -> str:
        assert cwd.is_dir()
        assert "产品助手" in developer_instructions
        assert "禁止提前撰写白盒摘要或完整 PRD" in developer_instructions
        self.started_instructions.append(developer_instructions)
        return "thread-product-1"

    def resume_thread(
        self,
        thread_id: str,
        *,
        cwd: Path,
        developer_instructions: str,
    ) -> None:
        assert cwd.is_dir()
        assert developer_instructions
        self.resumed.append(thread_id)

    def run_turn(
        self,
        thread_id: str,
        message: str,
        *,
        output_schema: dict[str, Any] | None = None,
        on_reasoning_summary: Callable[[str], None] | None = None,
    ) -> CodexTurnResult:
        self.turns += 1
        self.messages.append(message)
        assert thread_id == "thread-product-1"
        assert message
        assert output_schema and "properties" in output_schema
        if on_reasoning_summary is not None:
            on_reasoning_summary("正在识别目标用户与核心问题。\n")
            on_reasoning_summary("正在收敛首版范围与验收标准。")
        ready = self.turns >= 2
        payload = {
            "reply": "信息已经足够，我整理好了首版 PRD。" if ready else "首版最希望谁来使用？",
            "prd_ready": ready,
            "question": None
            if ready
            else {
                "mode": "single",
                "prompt": "首版最希望谁来使用？",
                "options": ["独立产品经理", "产品团队", "用户研究员", "其他，需要补充说明"],
            },
            "prd": {
                "title": "访谈洞察助手 PRD",
                "summary": "把访谈记录整理成结构化洞察。",
                "target_users": ["独立产品经理"],
                "problem": "人工整理访谈耗时且容易遗漏。",
                "core_flow": ["粘贴访谈", "生成洞察", "确认结果"],
                "features": ["文本输入", "结构化洞察"],
                "scope": {"included": ["文本访谈"], "excluded": ["音视频转写"]},
                "acceptance_criteria": ["一分钟内得到可复制的洞察"],
                "assumptions": ["首版只支持中文文本"],
                "source_notes": [message],
                "full_document": {
                    "product_goal": "让产品经理在一分钟内把访谈文本整理成可复制洞察",
                    "success_definition": "一分钟内得到可复制结果",
                    "usage_context": ["独立产品经理", "按访谈项目使用"],
                    "interaction_model": "同步单用户交互",
                    "inputs": ["中文访谈文本"],
                    "end_to_end_loop": ["粘贴访谈", "生成洞察", "确认并复制结果"],
                    "deliverables": ["结构化访谈洞察"],
                    "functional_requirements": ["文本输入", "结构化洞察"],
                    "non_functional_requirements": ["一分钟内完成处理"],
                    "external_actions": ["无 / N/A"],
                    "domain_knowledge": ["访谈主题、证据和行动建议的整理规则"],
                    "data_and_state": ["当前输入与生成结果"],
                    "boundaries": ["不处理音视频转写"],
                    "constraints": ["首版只支持中文文本"],
                    "failure_strategies": [
                        {
                            "scenario": "输入为空或生成失败",
                            "fallback": "保留输入并提示用户修改或重试",
                        }
                    ],
                    "success_metrics": [
                        {
                            "metric": "结果生成时延",
                            "target": "一分钟内",
                            "measurement": "记录提交到结果可复制的耗时",
                        }
                    ],
                    "harness": {
                        "tools": ["无 / N/A"],
                        "knowledge": ["访谈洞察结构规则"],
                        "observation": ["生成时延与结果字段完整性"],
                        "actions": ["整理并输出结构化洞察"],
                        "permissions": ["不访问用户未提交的数据"],
                    },
                    "open_questions": ["跨会话保存方式待确认"],
                    "traceability": [message],
                },
            }
            if ready
            else None,
        }
        if "question" in output_schema["properties"]:
            payload = {key: payload[key] for key in ("reply", "prd_ready", "question")}
        else:
            assert payload["prd"] is not None
            payload = {
                "reply": "信息已经足够，我整理好了首版 PRD。",
                "prd": PrdContent.model_validate(payload["prd"]).model_dump(
                    mode="json", exclude={"revision_notes", "generation"}
                ),
            }
        return CodexTurnResult(
            thread_id=thread_id,
            turn_id=f"turn-{self.turns}",
            text=json.dumps(payload, ensure_ascii=False),
        )


class BlockingCodexConversationBridge(FakeCodexConversationBridge):
    def __init__(self) -> None:
        super().__init__()
        self.started = Event()
        self.release = Event()

    def run_turn(
        self,
        thread_id: str,
        message: str,
        *,
        output_schema: dict[str, Any] | None = None,
        on_reasoning_summary: Callable[[str], None] | None = None,
    ) -> CodexTurnResult:
        self.started.set()
        assert self.release.wait(timeout=5), "test did not release the background Codex turn"
        return super().run_turn(
            thread_id,
            message,
            output_schema=output_schema,
            on_reasoning_summary=on_reasoning_summary,
        )


def test_codex_output_schema_is_strict_for_every_object() -> None:
    non_strict_paths: list[str] = []

    def visit(value: object, path: str = "$") -> None:
        if isinstance(value, dict):
            if value.get("type") == "object" and value.get("additionalProperties") is not False:
                non_strict_paths.append(path)
            for key, child in value.items():
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(CodexRequirementDecisionOutput.model_json_schema(), "$.decision")
    visit(CodexRequirementOutput.model_json_schema(), "$.generation")
    assert non_strict_paths == []


def test_codex_conversation_persists_thread_messages_and_prd(
    app: FastAPI,
    client: TestClient,
    api: ApiHarness,
) -> None:
    bridge = FakeCodexConversationBridge()
    app.state.codex_auth_bridge = bridge
    token, _user = api.login()
    project = api.create_project(token)

    initial = client.get(f"/api/v1/projects/{project['id']}/codex/conversation")
    assert initial.status_code == 200, initial.text
    assert initial.json()["thread_id"] is None
    assert initial.json()["messages"][0]["id"] == "welcome"

    first = client.post(
        f"/api/v1/projects/{project['id']}/codex/messages",
        json={"message": "主要给独立产品经理使用"},
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert first_payload["status"] == "question"
    assert first_payload["artifact"] is None
    assert first_payload["current_question"] == {
        "mode": "single",
        "prompt": "首版最希望谁来使用？",
        "options": ["独立产品经理", "产品团队", "用户研究员", "其他，需要补充说明"],
    }
    assert first_payload["thread_id"] == "thread-product-1"
    assert first_payload["draft"] is None

    second = client.post(
        f"/api/v1/projects/{project['id']}/codex/messages",
        json={"message": "核心标准是一分钟内得到可复制结果"},
    )
    assert second.status_code == 200, second.text
    second_payload = second.json()
    assert second_payload["status"] == "prd_ready"
    assert second_payload["current_question"] is None
    assert second_payload["artifact"]["type"] == "prd"
    assert second_payload["artifact"]["content"]["full_document"]["product_goal"]
    assert second_payload["artifact"]["content"]["full_document"]["harness"]["tools"] == [
        "无 / N/A"
    ]
    blueprint = second_payload["artifact"]["content"]["full_document"]["blueprint_process"]
    assert blueprint["blueprint_source"] == "agent-blueprint/BLUEPRINT.md"
    assert len(blueprint["layered_architecture"]) == 7
    assert blueprint["code_generation_plan"]["confirmation_gate"]
    assert "### Step 2：领域建模" in bridge.messages[-1]
    assert "### Step 4：架构设计" in bridge.messages[-1]
    assert "## 七、交付方式：先方案，后代码" in bridge.messages[-1]
    assert "蓝图是生成完整 PRD 时使用的内部推导规范" in bridge.messages[-1]
    assert "用户换成其他项目时" in bridge.messages[-1]
    assert second_payload["project"]["stage"] == "PRD_REVIEW"
    assert bridge.resumed == ["thread-product-1"]

    restored = client.get(f"/api/v1/projects/{project['id']}/codex/conversation")
    assert restored.status_code == 200, restored.text
    restored_payload = restored.json()
    assert restored_payload["thread_id"] == "thread-product-1"
    assert [item["role"] for item in restored_payload["messages"]] == [
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_codex_reasoning_summary_progress_is_available_to_the_project_owner(
    app: FastAPI,
    client: TestClient,
    api: ApiHarness,
) -> None:
    app.state.codex_auth_bridge = FakeCodexConversationBridge()
    token, _user = api.login()
    project = api.create_project(token)
    progress_id = "reasoning-progress-001"

    response = client.post(
        f"/api/v1/projects/{project['id']}/codex/messages",
        json={
            "message": "主要给独立产品经理使用",
            "progress_id": progress_id,
        },
    )
    assert response.status_code == 200, response.text

    progress = client.get(f"/api/v1/projects/{project['id']}/codex/reasoning/{progress_id}")
    assert progress.status_code == 200, progress.text
    assert progress.json() == {
        "status": "completed",
        "summary": "正在识别目标用户与核心问题。\n正在收敛首版范围与验收标准。",
    }


def test_codex_conversations_can_be_created_listed_and_restored(
    app: FastAPI,
    client: TestClient,
    api: ApiHarness,
) -> None:
    app.state.codex_auth_bridge = FakeCodexConversationBridge()
    token, _user = api.login()
    project = api.create_project(token)

    first_question = "给自由职业者做一个可以自动规划任务优先级并提醒截止时间的专注计时器"
    first = client.post(
        f"/api/v1/projects/{project['id']}/codex/messages",
        json={"message": first_question},
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()
    original_id = first_payload["conversation_id"]
    original_draft = first_payload["draft"]
    assert first_payload["title"] == first_question

    created = client.post(f"/api/v1/projects/{project['id']}/codex/conversations")
    assert created.status_code == 201, created.text
    created_payload = created.json()
    assert created_payload["conversation_id"] != original_id
    assert created_payload["title"] == "新对话"
    assert created_payload["thread_id"] is None
    assert created_payload["messages"] == [
        {
            "id": "welcome",
            "role": "assistant",
            "content": "把你的产品想法告诉我。我会一次只确认一个关键问题，并在右侧持续整理成 PRD。",
        }
    ]
    assert original_draft is None
    assert created_payload["draft"] is None

    conversations = client.get(f"/api/v1/projects/{project['id']}/codex/conversations")
    assert conversations.status_code == 200, conversations.text
    items = conversations.json()["items"]
    assert [item["id"] for item in items] == [created_payload["conversation_id"], original_id]
    assert items[0]["active"] is True
    assert items[0]["message_count"] == 0
    assert items[1]["active"] is False
    assert items[1]["message_count"] == 1

    restored = client.post(
        f"/api/v1/projects/{project['id']}/codex/conversations/{original_id}/activate"
    )
    assert restored.status_code == 200, restored.text
    restored_payload = restored.json()
    assert restored_payload["conversation_id"] == original_id
    assert restored_payload["thread_id"] == "thread-product-1"
    assert [item["role"] for item in restored_payload["messages"]] == [
        "assistant",
        "user",
        "assistant",
    ]

    refreshed = client.get(f"/api/v1/projects/{project['id']}/codex/conversation")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["conversation_id"] == original_id


def test_fresh_codex_conversation_does_not_inherit_the_project_idea(
    app: FastAPI,
    client: TestClient,
    api: ApiHarness,
) -> None:
    bridge = FakeCodexConversationBridge()
    app.state.codex_auth_bridge = bridge
    token, _user = api.login()
    project = api.create_project(token, idea="做一个香蕉专注时钟")

    created = client.post(f"/api/v1/projects/{project['id']}/codex/conversations")
    assert created.status_code == 201, created.text

    fresh_idea = "做一个 Web 西瓜学习计时助手"
    fresh_turn = client.post(
        f"/api/v1/projects/{project['id']}/codex/messages",
        json={"message": fresh_idea},
    )
    assert fresh_turn.status_code == 200, fresh_turn.text
    assert bridge.messages[-1] == fresh_idea
    assert "不得继承项目旧想法、旧 PRD" in bridge.started_instructions[-1]
    assert project["idea"] not in bridge.started_instructions[-1]


def test_codex_turn_keeps_running_and_returns_to_history_after_creating_a_new_conversation(
    app: FastAPI,
    client: TestClient,
    api: ApiHarness,
) -> None:
    bridge = BlockingCodexConversationBridge()
    app.state.codex_auth_bridge = bridge
    token, _user = api.login()
    project = api.create_project(token)
    original = client.get(f"/api/v1/projects/{project['id']}/codex/conversation").json()

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(
            client.post,
            f"/api/v1/projects/{project['id']}/codex/messages",
            json={"message": "做一个番茄闹钟 Web 端"},
        )
        assert bridge.started.wait(timeout=5), "background Codex turn did not start"

        created = client.post(f"/api/v1/projects/{project['id']}/codex/conversations")
        assert created.status_code == 201, created.text
        created_payload = created.json()
        assert created_payload["conversation_id"] != original["conversation_id"]
        assert created_payload["draft"] is None

        bridge.release.set()
        finished = pending.result(timeout=5)

    assert finished.status_code == 200, finished.text
    assert finished.json()["conversation_id"] == original["conversation_id"]

    active = client.get(f"/api/v1/projects/{project['id']}/codex/conversation")
    assert active.status_code == 200, active.text
    assert active.json()["conversation_id"] == created_payload["conversation_id"]
    assert active.json()["draft"] is None

    conversations = client.get(f"/api/v1/projects/{project['id']}/codex/conversations")
    assert conversations.status_code == 200, conversations.text
    items = conversations.json()["items"]
    background_item = next(item for item in items if item["id"] == original["conversation_id"])
    assert background_item["active"] is False
    assert background_item["message_count"] == 1

    restored = client.post(
        f"/api/v1/projects/{project['id']}/codex/conversations/{original['conversation_id']}/activate"
    )
    assert restored.status_code == 200, restored.text
    restored_payload = restored.json()
    assert restored_payload["draft"] is None
    assert restored_payload["current_question"]["prompt"] == "首版最希望谁来使用？"
    assert [item["role"] for item in restored_payload["messages"]] == [
        "assistant",
        "user",
        "assistant",
    ]
