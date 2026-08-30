from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol, TypeVar

import httpx

from app.core.config import Settings
from app.core.errors import ApiError
from app.prompts.coding_bundle import CODING_PROMPT_VERSION, CODING_SYSTEM_PROMPT
from app.prompts.controlled_text_agent import PROMPT_VERSION, SYSTEM_PROMPT
from app.prompts.product_artifacts import (
    PRD_PROMPT_VERSION,
    PRD_SYSTEM_PROMPT,
    SOLUTION_PROMPT_VERSION,
    SOLUTION_SYSTEM_PROMPT,
)
from app.schemas.contracts import (
    AgentResult,
    CodingBundle,
    GeneratedCodeFile,
    PrdContent,
    PreviewConfig,
    SolutionContent,
)
from app.services.vibe_frontend import build_vibe_html_bundle

ArtifactContent = TypeVar("ArtifactContent", PrdContent, SolutionContent)


@dataclass(frozen=True, slots=True)
class ProviderResult:
    result: AgentResult
    provider: str
    model: str
    provider_verification: str
    usage: dict[str, object]
    latency_ms: float


@dataclass(frozen=True, slots=True)
class ProviderCall:
    result: AgentResult
    usage: dict[str, object]


@dataclass(frozen=True, slots=True)
class ArtifactProviderCall:
    content: PrdContent | SolutionContent
    usage: dict[str, object]


@dataclass(frozen=True, slots=True)
class CodingBundleProviderCall:
    content: CodingBundle
    usage: dict[str, object]


class AIProvider(Protocol):
    name: str
    model: str
    verification: str

    def generate(self, user_input: str, config: PreviewConfig) -> ProviderCall: ...

    def write_prd(
        self, project_name: str, idea: str, requirement_text: str
    ) -> ArtifactProviderCall: ...

    def architect_solution(self, project_name: str, prd: PrdContent) -> ArtifactProviderCall: ...

    def build_code_bundle(
        self,
        project_name: str,
        idea: str,
        prd: PrdContent,
        solution: SolutionContent,
        product_context: dict[str, object],
    ) -> CodingBundleProviderCall: ...


class MockProvider:
    name = "mock"
    verification = "mock"

    def __init__(self, model: str) -> None:
        self.model = model

    def generate(self, user_input: str, config: PreviewConfig) -> ProviderCall:
        words = [part.strip("，。！？,.!? ") for part in user_input.replace("\n", " ").split(" ")]
        key_points = [part for part in words if part][:3]
        if not key_points:
            key_points = [user_input[:80]]
        return ProviderCall(
            result=AgentResult(
                summary=f"{config.title} 已处理你的输入：{user_input[:240]}",
                key_points=key_points,
                next_step="请检查结果是否符合目标；如需调整，可补充期望语气、对象或输出限制。",
            ),
            usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "estimated": True,
                "prompt_version": PROMPT_VERSION,
            },
        )

    @staticmethod
    def _summary(value: str, limit: int) -> str:
        normalized = " ".join(value.split())
        return normalized if len(normalized) <= limit else normalized[: limit - 1] + "…"

    def _usage(self, prompt_version: str) -> dict[str, object]:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated": True,
            "prompt_version": prompt_version,
        }

    def write_prd(
        self, project_name: str, idea: str, requirement_text: str
    ) -> ArtifactProviderCall:
        content = PrdContent(
            title=f"{project_name}｜M1 产品需求文档",
            summary=f"围绕“{self._summary(idea, 120)}”构建一个受控文本型 AI Web Agent。",
            target_users=["有明确业务目标、但无法独立完成 AI 产品开发的非技术用户"],
            problem=(
                "用户需要把输入内容转化为可直接使用的结构化结果。"
                f"补充说明：{self._summary(requirement_text, 220)}"
            ),
            core_flow=[
                "用户输入文本",
                "系统校验并调用配置模型",
                "展示结构化结果",
                "保存本次运行历史",
            ],
            features=[
                "单一文本输入",
                "结构化结果展示",
                "运行状态与产品语言错误",
                "同一预览内的历史记录",
            ],
            scope={
                "included": [
                    "文本输入",
                    "配置模型调用",
                    "结构化输出",
                    "历史记录",
                    "响应式 Web 预览",
                ],
                "excluded": [
                    "文件与 RAG",
                    "音视频生成",
                    "目标产品账户系统",
                    "支付",
                    "任意代码执行",
                ],
            },
            acceptance_criteria=[
                "用户可以提交非空文本并获得包含摘要、要点和下一步的结果",
                "刷新项目工作区后 PRD、方案、任务和确认记录仍然存在",
                "模型失败时显示可理解错误，不显示密钥或程序堆栈",
            ],
            assumptions=[
                "首版只支持文本型 AI Web Agent",
                "真实模型费用和效果必须由真实 Key 冒烟确认",
            ],
            source_notes=[self._summary(idea, 500), self._summary(requirement_text, 1_000)],
        )
        usage = self._usage(PRD_PROMPT_VERSION)
        content.generation = self._generation_metadata(usage)
        return ArtifactProviderCall(content=content, usage=usage)

    def architect_solution(self, project_name: str, prd: PrdContent) -> ArtifactProviderCall:
        content = SolutionContent.model_validate(
            {
                "title": f"{project_name}｜推荐产品与技术方案",
                "summary": "采用一个受控文本 Agent 模板完成首条纵向切片，先验证核心价值与结果质量。",
                "recommended_approach": "模块化单体：API、关系型业务状态和持久化任务；模型通过后端 provider 边界调用。",
                "product_scope": prd.scope["included"],
                "deferred": prd.scope["excluded"],
                "user_costs": [
                    {
                        "item": "本地 M1",
                        "estimate": "无新增云资源费用",
                        "note": "使用 SQLite 与本地受控预览",
                    },
                    {
                        "item": "真实模型",
                        "estimate": "按所选供应商实际用量",
                        "note": "启用前配置自己的 Key 并确认费用",
                    },
                ],
                "external_accounts": ["mock 验收无需外部账号；真实模型验收需要对应供应商账号"],
                "risks": [
                    "当前不是任意代码沙箱",
                    "本地预览不等于公网托管",
                    "模型效果仍需真实 Key 冒烟",
                ],
                "deliverables": [
                    "版本化 PRD",
                    "推荐方案",
                    "持久化开发任务",
                    "绑定代码版本的可操作文本 Agent 预览",
                ],
                "architecture": {
                    "application": "modular_monolith",
                    "backend": "FastAPI + SQLAlchemy",
                    "database": "SQLite for local M1",
                    "task_runtime": "persistent table + controlled single-process executor",
                    "preview_template": "controlled_text_agent_v1",
                },
            }
        )
        usage = self._usage(SOLUTION_PROMPT_VERSION)
        content.generation = self._generation_metadata(usage)
        return ArtifactProviderCall(content=content, usage=usage)

    def build_code_bundle(
        self,
        project_name: str,
        idea: str,
        prd: PrdContent,
        solution: SolutionContent,
        product_context: dict[str, object],
    ) -> CodingBundleProviderCall:
        bundle, usage = build_vibe_html_bundle(
            provider_name=self.name,
            model=self.model,
            verification=self.verification,
            project_name=project_name,
            idea=idea,
            prd=prd,
            solution=solution,
            product_context=product_context,
        )
        return CodingBundleProviderCall(content=bundle, usage=usage)

        # Kept as a compatibility reference for repositories generated before
        # the HTML product template was introduced.
        project_literal = json.dumps(project_name, ensure_ascii=False)
        idea_literal = json.dumps(self._summary(idea, 240), ensure_ascii=False)
        manifest = {
            "template": "controlled_text_agent_backend_v1",
            "project_name": project_name,
            "idea": idea,
            "prd_title": prd.title,
            "solution_title": solution.title,
            "product_context": product_context,
            "verification": "generated_not_tested",
        }
        files = [
            GeneratedCodeFile(
                path="README.md",
                language="markdown",
                product_purpose="告诉接手者这个后端解决什么问题、怎样启动以及当前未验内容。",
                content=(
                    f"# {project_name}\n\n{idea}\n\n"
                    "## 当前能力\n\n- 文本输入\n- 结构化处理结果\n- 本地历史记录\n\n"
                    "## 启动\n\n```bash\nuv sync\nuv run uvicorn app.main:app --reload\n```\n\n"
                    "> 这是第三阶段生成的代码版本，尚未通过第四阶段的完整测试与公网预览验收。\n"
                ),
            ),
            GeneratedCodeFile(
                path="pyproject.toml",
                language="toml",
                product_purpose="固定生成产品后端的 Python 版本、运行依赖和测试依赖。",
                content=(
                    "[project]\nname = \"generated-text-agent\"\nversion = \"0.1.0\"\n"
                    "requires-python = \">=3.11,<3.12\"\n"
                    "dependencies = [\"fastapi>=0.115,<1\", \"pydantic>=2.10,<3\", "
                    "\"httpx>=0.27,<1\", \"uvicorn[standard]>=0.32,<1\"]\n\n"
                    "[dependency-groups]\ndev = [\"httpx>=0.27,<1\", \"pytest>=8.3,<9\"]\n\n"
                    "[tool.pytest.ini_options]\ntestpaths = [\"tests\"]\n"
                ),
            ),
            GeneratedCodeFile(
                path=".gitignore",
                language="gitignore",
                product_purpose="阻止密钥、本地数据库和缓存进入源码版本。",
                content=".env\n.venv/\n__pycache__/\n*.pyc\ndata/\n.pytest_cache/\n",
            ),
            GeneratedCodeFile(
                path="app/__init__.py",
                language="python",
                product_purpose="声明后端应用包。",
                content='"""Generated text Agent backend."""\n',
            ),
            GeneratedCodeFile(
                path="app/schemas.py",
                language="python",
                product_purpose="用精确结构约束用户输入和 Agent 输出。",
                content=(
                    "from pydantic import BaseModel, Field\n\n\n"
                    "class AnalyzeRequest(BaseModel):\n"
                    "    input: str = Field(min_length=1, max_length=5000)\n\n\n"
                    "class AnalyzeResponse(BaseModel):\n"
                    "    summary: str\n"
                    "    key_points: list[str]\n"
                    "    next_step: str\n\n\n"
                    "class HistoryItem(AnalyzeResponse):\n"
                    "    id: int\n"
                    "    input: str\n"
                ),
            ),
            GeneratedCodeFile(
                path="app/provider.py",
                language="python",
                product_purpose="把运行时模型封装在后端，通过环境配置切换 mock 或真实兼容接口。",
                content=(
                    "import os\n\n"
                    "import httpx\n\n"
                    "from app.schemas import AnalyzeResponse\n\n\n"
                    "def generate_result(value: str, project_name: str) -> AnalyzeResponse:\n"
                    "    provider = os.getenv('PRODUCT_AGENT_PROVIDER', 'mock')\n"
                    "    if provider == 'mock':\n"
                    "        chunks = [item for item in value.replace('，', ' ').split(' ') if item]\n"
                    "        return AnalyzeResponse(\n"
                    "            summary=f'{project_name} 已整理输入：{value[:240]}',\n"
                    "            key_points=chunks[:3] or [value[:80]],\n"
                    "            next_step='请检查结果是否符合目标；真实模型需单独配置并完成冒烟。',\n"
                    "        )\n"
                    "    api_key = os.getenv('PRODUCT_AGENT_API_KEY', '')\n"
                    "    base_url = os.getenv('PRODUCT_AGENT_BASE_URL', '').rstrip('/')\n"
                    "    model = os.getenv('PRODUCT_AGENT_MODEL', '')\n"
                    "    if provider != 'openai_compatible' or not api_key or not base_url or not model:\n"
                    "        raise RuntimeError('runtime model provider is not configured')\n"
                    "    response = httpx.post(\n"
                    "        f'{base_url}/chat/completions',\n"
                    "        headers={'Authorization': f'Bearer {api_key}'},\n"
                    "        json={\n"
                    "            'model': model,\n"
                    "            'response_format': {'type': 'json_object'},\n"
                    "            'messages': [\n"
                    "                {'role': 'system', 'content': 'Return JSON with summary, key_points and next_step.'},\n"
                    "                {'role': 'user', 'content': value},\n"
                    "            ],\n"
                    "        },\n"
                    "        timeout=30,\n"
                    "    )\n"
                    "    response.raise_for_status()\n"
                    "    content = response.json()['choices'][0]['message']['content']\n"
                    "    return AnalyzeResponse.model_validate_json(content)\n"
                ),
            ),
            GeneratedCodeFile(
                path="app/service.py",
                language="python",
                product_purpose="集中承载文本 Agent 的核心处理能力，后续可替换为真实模型适配器。",
                content=(
                    "from app.provider import generate_result\n"
                    "from app.schemas import AnalyzeResponse\n\n"
                    f"PROJECT_NAME = {project_literal}\n"
                    f"PRODUCT_IDEA = {idea_literal}\n\n\n"
                    "def analyze_text(value: str) -> AnalyzeResponse:\n"
                    "    normalized = ' '.join(value.split())\n"
                    "    return generate_result(normalized, PROJECT_NAME)\n"
                ),
            ),
            GeneratedCodeFile(
                path="app/repository.py",
                language="python",
                product_purpose="把运行历史保存在本地 SQLite，刷新后仍可查询。",
                content=(
                    "import json\nimport sqlite3\nfrom pathlib import Path\n\n"
                    "DB_PATH = Path('data/history.db')\n\n\n"
                    "def _connect() -> sqlite3.Connection:\n"
                    "    DB_PATH.parent.mkdir(parents=True, exist_ok=True)\n"
                    "    connection = sqlite3.connect(DB_PATH)\n"
                    "    connection.row_factory = sqlite3.Row\n"
                    "    connection.execute(\n"
                    "        'CREATE TABLE IF NOT EXISTS runs '\n"
                    "        '(id INTEGER PRIMARY KEY, input TEXT NOT NULL, output_json TEXT NOT NULL)'\n"
                    "    )\n"
                    "    return connection\n\n\n"
                    "def save_run(input_text: str, output: dict) -> int:\n"
                    "    with _connect() as connection:\n"
                    "        cursor = connection.execute('INSERT INTO runs(input, output_json) VALUES (?, ?)', "
                    "(input_text, json.dumps(output, ensure_ascii=False)))\n"
                    "        return int(cursor.lastrowid)\n\n\n"
                    "def list_runs() -> list[dict]:\n"
                    "    with _connect() as connection:\n"
                    "        rows = connection.execute('SELECT id, input, output_json FROM runs ORDER BY id DESC').fetchall()\n"
                    "    return [{'id': row['id'], 'input': row['input'], "
                    "**json.loads(row['output_json'])} for row in rows]\n"
                ),
            ),
            GeneratedCodeFile(
                path="app/main.py",
                language="python",
                product_purpose="提供健康检查、文本处理和历史记录三个受控 API。",
                content=(
                    "from fastapi import FastAPI\n\n"
                    "from app.repository import list_runs, save_run\n"
                    "from app.schemas import AnalyzeRequest, AnalyzeResponse, HistoryItem\n"
                    "from app.service import analyze_text\n\n"
                    f"app = FastAPI(title={project_literal}, version='0.1.0')\n\n\n"
                    "@app.get('/api/v1/health')\n"
                    "def health() -> dict[str, str]:\n"
                    "    return {'status': 'ok'}\n\n\n"
                    "@app.post('/api/v1/analyze', response_model=AnalyzeResponse)\n"
                    "def analyze(body: AnalyzeRequest) -> AnalyzeResponse:\n"
                    "    result = analyze_text(body.input)\n"
                    "    save_run(body.input, result.model_dump())\n"
                    "    return result\n\n\n"
                    "@app.get('/api/v1/history', response_model=list[HistoryItem])\n"
                    "def history() -> list[dict]:\n"
                    "    return list_runs()\n"
                ),
            ),
            GeneratedCodeFile(
                path="tests/test_contract.py",
                language="python",
                product_purpose="定义下一阶段必须真正运行的核心接口验收用例。",
                content=(
                    "from fastapi.testclient import TestClient\n\n"
                    "from app.main import app\n\n"
                    "client = TestClient(app)\n\n\n"
                    "def test_health_and_analyze(tmp_path, monkeypatch):\n"
                    "    monkeypatch.chdir(tmp_path)\n"
                    "    assert client.get('/api/v1/health').json() == {'status': 'ok'}\n"
                    "    response = client.post('/api/v1/analyze', json={'input': '一次真实产品访谈'})\n"
                    "    assert response.status_code == 200\n"
                    "    assert response.json()['summary']\n"
                ),
            ),
            GeneratedCodeFile(
                path="product_factory.json",
                language="json",
                product_purpose="记录本次代码由哪些确认产物和产品决策生成，便于追溯。",
                content=json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            ),
        ]
        usage = self._usage(CODING_PROMPT_VERSION)
        content = CodingBundle(
            summary=f"已为“{project_name}”生成受控文本 Agent 后端代码包。",
            files=files,
            run_instructions=[
                "使用 Python 3.11 创建隔离环境",
                "安装 pyproject.toml 中的锁定范围依赖",
                "第四阶段运行 pytest、启动服务并执行浏览器验收",
            ],
            generation=self._generation_metadata(usage),
        )
        return CodingBundleProviderCall(content=content, usage=usage)

    def _generation_metadata(self, usage: dict[str, object]) -> dict[str, object]:
        return {
            "provider": self.name,
            "model": self.model,
            "provider_verification": self.verification,
            "usage": usage,
        }


class OpenAICompatibleProvider:
    """Raw compatible HTTP boundary; unverified until an operator records a real smoke."""

    name = "openai_compatible"

    def __init__(
        self,
        settings: Settings,
        *,
        api_key_override: str | None = None,
        model_override: str | None = None,
        verification_override: str | None = None,
    ) -> None:
        self.model = model_override or settings.ai_model
        self.base_url = settings.ai_base_url.rstrip("/")
        self.api_key = (
            api_key_override
            if api_key_override is not None
            else settings.ai_api_key.get_secret_value()
        )
        self.timeout = settings.ai_timeout_seconds
        self.verification = verification_override or (
            "verified" if settings.ai_provider_verified else "unverified"
        )

    def generate(self, user_input: str, config: PreviewConfig) -> ProviderCall:
        if not self.api_key:
            raise ApiError("PROVIDER_NOT_CONFIGURED", "真实模型尚未配置，请联系管理员。", 503)
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {"role": "user", "content": user_input},
            ],
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ApiError("PROVIDER_TIMEOUT", "模型响应超时，请稍后重试。", 504) from exc
        except httpx.HTTPError as exc:
            raise ApiError("PROVIDER_UNAVAILABLE", "模型服务暂时不可用，请稍后重试。", 502) from exc

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content) if isinstance(content, str) else content
            usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
            return ProviderCall(
                result=AgentResult.model_validate(parsed),
                usage={**usage, "prompt_version": PROMPT_VERSION},
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ApiError(
                "PROVIDER_INVALID_OUTPUT", "模型返回格式不符合预期，请重试。", 502
            ) from exc

    def _structured_artifact(
        self,
        *,
        system_prompt: str,
        prompt_version: str,
        user_payload: dict[str, object],
        schema: type[ArtifactContent],
    ) -> ArtifactProviderCall:
        if not self.api_key:
            raise ApiError("PROVIDER_NOT_CONFIGURED", "真实模型尚未配置，请联系管理员。", 503)
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "input": user_payload,
                            "required_json_schema": schema.model_json_schema(),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ApiError("PROVIDER_TIMEOUT", "模型响应超时，请稍后重试。", 504) from exc
        except httpx.HTTPError as exc:
            raise ApiError("PROVIDER_UNAVAILABLE", "模型服务暂时不可用，请稍后重试。", 502) from exc
        try:
            body = response.json()
            raw_content = body["choices"][0]["message"]["content"]
            parsed = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
            content = schema.model_validate(parsed)
            raw_usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
            usage: dict[str, object] = {**raw_usage, "prompt_version": prompt_version}
            content.generation = {
                "provider": self.name,
                "model": self.model,
                "provider_verification": self.verification,
                "usage": usage,
            }
            return ArtifactProviderCall(content=content, usage=usage)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ApiError(
                "PROVIDER_INVALID_OUTPUT", "模型返回格式不符合预期，请重试。", 502
            ) from exc

    def write_prd(
        self, project_name: str, idea: str, requirement_text: str
    ) -> ArtifactProviderCall:
        return self._structured_artifact(
            system_prompt=PRD_SYSTEM_PROMPT,
            prompt_version=PRD_PROMPT_VERSION,
            user_payload={
                "project_name": project_name,
                "idea": idea,
                "requirement_answers": requirement_text,
            },
            schema=PrdContent,
        )

    def architect_solution(self, project_name: str, prd: PrdContent) -> ArtifactProviderCall:
        return self._structured_artifact(
            system_prompt=SOLUTION_SYSTEM_PROMPT,
            prompt_version=SOLUTION_PROMPT_VERSION,
            user_payload={"project_name": project_name, "prd": prd.model_dump(mode="json")},
            schema=SolutionContent,
        )

    def build_code_bundle(
        self,
        project_name: str,
        idea: str,
        prd: PrdContent,
        solution: SolutionContent,
        product_context: dict[str, object],
    ) -> CodingBundleProviderCall:
        if not self.api_key:
            raise ApiError("PROVIDER_NOT_CONFIGURED", "真实模型尚未配置，请联系管理员。", 503)
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": CODING_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "input": {
                                "project_name": project_name,
                                "idea": idea,
                                "prd": prd.model_dump(mode="json"),
                                "solution": solution.model_dump(mode="json"),
                                "product_context": product_context,
                            },
                            "required_json_schema": CodingBundle.model_json_schema(),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ApiError("PROVIDER_TIMEOUT", "模型响应超时，请稍后重试。", 504) from exc
        except httpx.HTTPError as exc:
            raise ApiError("PROVIDER_UNAVAILABLE", "模型服务暂时不可用，请稍后重试。", 502) from exc
        try:
            body = response.json()
            raw_content = body["choices"][0]["message"]["content"]
            parsed = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
            content = CodingBundle.model_validate(parsed)
            raw_usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
            usage: dict[str, object] = {
                **raw_usage,
                "prompt_version": CODING_PROMPT_VERSION,
            }
            content.generation = {
                "provider": self.name,
                "model": self.model,
                "provider_verification": self.verification,
                "usage": usage,
            }
            return CodingBundleProviderCall(content=content, usage=usage)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ApiError(
                "PROVIDER_INVALID_OUTPUT", "模型返回的代码包格式不符合约束，请重试。", 502
            ) from exc


def build_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == "mock":
        return MockProvider(settings.ai_model)
    if settings.ai_provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleProvider(settings)
    raise ValueError(f"Unsupported AI_PROVIDER: {settings.ai_provider}")


def build_user_provider(
    settings: Settings,
    *,
    provider: str,
    api_key: str,
    model: str,
    verified: bool,
) -> AIProvider:
    if provider != "openai_compatible":
        raise ApiError("UNSUPPORTED_MODEL_PROVIDER", "当前模型供应商暂不支持。", 422)
    return OpenAICompatibleProvider(
        settings,
        api_key_override=api_key,
        model_override=model,
        verification_override="verified" if verified else "unverified",
    )


def generate_with_retry(
    provider: AIProvider,
    *,
    user_input: str,
    config: PreviewConfig,
    max_attempts: int,
) -> ProviderResult:
    started = time.perf_counter()
    last_error: ApiError | None = None
    for _attempt in range(1, max_attempts + 1):
        try:
            call = provider.generate(user_input, config)
            result = AgentResult.model_validate(call.result)
            return ProviderResult(
                result=result,
                provider=provider.name,
                model=provider.model,
                provider_verification=provider.verification,
                usage={**call.usage, "provider_verification": provider.verification},
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        except ApiError as exc:
            last_error = exc
            if exc.code not in {
                "PROVIDER_TIMEOUT",
                "PROVIDER_UNAVAILABLE",
                "PROVIDER_INVALID_OUTPUT",
            }:
                raise
    assert last_error is not None
    raise last_error


def write_prd_with_retry(
    provider: AIProvider,
    *,
    project_name: str,
    idea: str,
    requirement_text: str,
    max_attempts: int,
) -> PrdContent:
    last_error: ApiError | None = None
    for _attempt in range(1, max_attempts + 1):
        try:
            call = provider.write_prd(project_name, idea, requirement_text)
            return PrdContent.model_validate(call.content)
        except ApiError as exc:
            last_error = exc
            if exc.code not in {
                "PROVIDER_TIMEOUT",
                "PROVIDER_UNAVAILABLE",
                "PROVIDER_INVALID_OUTPUT",
            }:
                raise
    assert last_error is not None
    raise last_error


def architect_solution_with_retry(
    provider: AIProvider,
    *,
    project_name: str,
    prd: PrdContent,
    max_attempts: int,
) -> SolutionContent:
    last_error: ApiError | None = None
    for _attempt in range(1, max_attempts + 1):
        try:
            call = provider.architect_solution(project_name, prd)
            return SolutionContent.model_validate(call.content)
        except ApiError as exc:
            last_error = exc
            if exc.code not in {
                "PROVIDER_TIMEOUT",
                "PROVIDER_UNAVAILABLE",
                "PROVIDER_INVALID_OUTPUT",
            }:
                raise
    assert last_error is not None
    raise last_error


def build_code_bundle_with_retry(
    provider: AIProvider,
    *,
    project_name: str,
    idea: str,
    prd: PrdContent,
    solution: SolutionContent,
    product_context: dict[str, object],
    max_attempts: int,
) -> CodingBundleProviderCall:
    last_error: ApiError | None = None
    for _attempt in range(1, max_attempts + 1):
        try:
            call = provider.build_code_bundle(
                project_name,
                idea,
                prd,
                solution,
                product_context,
            )
            return CodingBundleProviderCall(
                content=CodingBundle.model_validate(call.content),
                usage=call.usage,
            )
        except ApiError as exc:
            last_error = exc
            if exc.code not in {
                "PROVIDER_TIMEOUT",
                "PROVIDER_UNAVAILABLE",
                "PROVIDER_INVALID_OUTPUT",
            }:
                raise
    assert last_error is not None
    raise last_error
