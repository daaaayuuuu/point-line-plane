from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.models import Project
from app.schemas.contracts import PrdBlueprintProcess, PrdContent, PrdFullDocument
from app.services.codex_auth import CodexAuthBridge, CodexAuthError

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


class CodexScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    included: list[str]
    excluded: list[str]


class CodexPrdFullDocument(PrdFullDocument):
    blueprint_process: PrdBlueprintProcess


class CodexPrdDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str
    target_users: list[str]
    problem: str
    core_flow: list[str]
    features: list[str]
    scope: CodexScope
    acceptance_criteria: list[str]
    assumptions: list[str]
    source_notes: list[str]
    full_document: CodexPrdFullDocument


class CodexClarifyingQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["single", "multiple"]
    prompt: str = Field(min_length=1)
    options: list[str] = Field(min_length=3, max_length=6)


class CodexRequirementDecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply: str = Field(min_length=1)
    prd_ready: bool
    question: CodexClarifyingQuestion | None

    @model_validator(mode="after")
    def validate_turn_shape(self) -> CodexRequirementDecisionOutput:
        if self.prd_ready and self.question is not None:
            raise ValueError("ready decisions must not include a clarifying question")
        if not self.prd_ready and self.question is None:
            raise ValueError("clarifying decisions require a question")
        return self


class CodexRequirementOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply: str = Field(min_length=1)
    prd: CodexPrdDraft


@dataclass(frozen=True, slots=True)
class CodexRequirementResult:
    thread_id: str
    turn_id: str
    reply: str
    prd_ready: bool
    question: CodexClarifyingQuestion | None
    prd: PrdContent | None


@lru_cache(maxsize=1)
def _prd_blueprint_guidance() -> str:
    service_path = Path(__file__).resolve()
    blueprint_paths = (
        service_path.parents[3] / "agent-blueprint" / "BLUEPRINT.md",
        service_path.parents[4] / "agent-blueprint" / "BLUEPRINT.md",
    )
    for blueprint_path in blueprint_paths:
        try:
            return blueprint_path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return ""


def _developer_instructions(project: Project, *, include_project_idea: bool) -> str:
    project_idea_context = (
        f"用户创建项目时最初记录的产品想法：{project.idea}\n"
        if include_project_idea
        else "这是用户主动新建的独立对话，不得继承项目旧想法、旧 PRD 的主题、命名、功能或奖励机制。\n"
    )
    return f"""你是点线面的 Codex 产品助手，负责通过简洁中文对话把产品想法整理成可执行 PRD。

当前项目名称：{project.name}
{project_idea_context}

工作规则：
1. 不要调用终端、文件、网络或其他工具，只进行产品需求分析。
2. 每次只追问一个最关键的问题；如果目标用户、核心痛点、首版范围和验收方式已足够明确，就不再追问。
3. 每一轮先只判断是否还需要澄清；信息不足时只生成 reply 和下一道 question，禁止提前撰写白盒摘要或完整 PRD。
4. prd_ready 只有在 PRD 已足够让用户检查确认时才为 true；最多经过两次聚焦追问后应基于合理假设生成可确认版本。
5. reply 是直接展示给用户的自然中文，不要包含 JSON、Markdown 代码块或内部说明。
6. 当 prd_ready 为 false 时，question 必须提供当前追问的结构化回答方式：只能选一个时 mode 为 single，可组合选择时 mode 为 multiple，并给出 3 至 6 个简短、互不重复、可直接提交的中文选项；最后一个选项可用于“其他，需要补充说明”。
7. 当 prd_ready 为 true 时，question 必须为 null；当 prd_ready 为 false 时，question 必须存在。
8. 最终回复必须严格匹配客户端提供的 JSON Schema。
9. 如果系统生成面向用户的推理摘要，只使用简洁中文描述当前正在分析的产品问题，不输出英文。
10. 当前对话中用户最新表达的产品对象和主题拥有最高优先级；出现冲突时必须舍弃旧名称、旧主题和旧功能，不得混用（例如西瓜不能被旧对话里的香蕉替换）。
"""


def _decode_structured_output(
    raw: str,
    output_type: type[StructuredOutput],
) -> StructuredOutput:
    candidate = raw.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        payload = json.loads(candidate)
        return output_type.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise CodexAuthError("Codex 返回的 PRD 结构无效，请重试。") from exc


def run_codex_requirement_turn(
    bridge: CodexAuthBridge,
    project: Project,
    *,
    message: str,
    thread_id: str | None,
    workspace: Path,
    on_reasoning_summary: Callable[[str], None] | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    include_project_idea: bool = True,
) -> CodexRequirementResult:
    workspace.mkdir(parents=True, exist_ok=True)
    instructions = _developer_instructions(project, include_project_idea=include_project_idea)
    active_thread_id = thread_id
    if active_thread_id:
        try:
            bridge.resume_thread(
                active_thread_id,
                cwd=workspace,
                developer_instructions=instructions,
            )
        except CodexAuthError:
            active_thread_id = None
    if not active_thread_id:
        active_thread_id = bridge.start_thread(
            cwd=workspace,
            developer_instructions=instructions,
        )

    turn_options: dict[str, object] = {
        "output_schema": CodexRequirementDecisionOutput.model_json_schema()
    }
    if on_reasoning_summary is not None:
        turn_options["on_reasoning_summary"] = on_reasoning_summary
    if model is not None:
        turn_options["model"] = model
    if reasoning_effort is not None:
        turn_options["reasoning_effort"] = "low"
    decision_turn = bridge.run_turn(active_thread_id, message, **turn_options)
    decision = _decode_structured_output(decision_turn.text, CodexRequirementDecisionOutput)
    if not decision.prd_ready:
        return CodexRequirementResult(
            thread_id=active_thread_id,
            turn_id=decision_turn.turn_id,
            reply=decision.reply,
            prd_ready=False,
            question=decision.question,
            prd=None,
        )

    blueprint_guidance = _prd_blueprint_guidance()
    generation_prompt = f"""信息已经足够。现在根据本对话一次性生成白盒确认摘要和供后续流程读取的完整 PRD。
prd 顶层字段只承载右侧白盒确认摘要；full_document 才是完整 PRD，二者不能只是同一内容的重复排版。
full_document 必须写清目标与成功定义、用户与使用方式、输入到交付物的闭环、功能与非功能需求、外部动作、领域知识、数据状态、边界约束、失败降级、成功指标、Harness 五要素、待确认项和来源追溯。
full_document.blueprint_process 必须严格按蓝图五步 SOP 继续产出：组件选型、7 层分层架构与跨层数据流、逐项工具清单、系统提示词草案、上下文与记忆、权限安全、可观测性、技术栈与部署形态，以及骨架→硬化→产品化的代码生成计划。
蓝图是生成完整 PRD 时使用的内部推导规范，不是面向用户的 PRD 章节模板。full_document 的所有正文必须针对本轮对话中的当前产品撰写；不得把“Step 1～Step 5”、蓝图章节名或通用蓝图说明当作 PRD 正文。用户换成其他项目时，必须重新基于新对话生成新项目的完整 PRD，不能沿用当前产品内容。
组件只选择当前 PRD 真正需要的；不需要的要明确写 not_selected，证据不足写 pending。7 层都必须出现，简单产品允许某层写“无 / N/A”。只写代码生成计划，方案确认前不得生成实际产品代码。
没有得到用户确认的事实必须写“待确认”，不得为了填满结构而脑补。简单产品允许 Harness 某项写“无 / N/A”。

以下内容来自项目的 Agent 产品架构蓝图，只作为完整 PRD 的生成规范；不要把蓝图原文直接复述给用户：
{blueprint_guidance}
"""
    generation_options = {
        **turn_options,
        "output_schema": CodexRequirementOutput.model_json_schema(),
    }
    if reasoning_effort is not None:
        generation_options["reasoning_effort"] = reasoning_effort
    generation_turn = bridge.run_turn(active_thread_id, generation_prompt, **generation_options)
    output = _decode_structured_output(generation_turn.text, CodexRequirementOutput)
    prd = PrdContent.model_validate(
        {
            **output.prd.model_dump(mode="json"),
            "revision_notes": [],
            "generation": {
                "provider": "codex_app_server",
                "thread_id": active_thread_id,
                "turn_id": generation_turn.turn_id,
            },
        }
    )
    return CodexRequirementResult(
        thread_id=active_thread_id,
        turn_id=generation_turn.turn_id,
        reply=output.reply,
        prd_ready=True,
        question=None,
        prd=prd,
    )
