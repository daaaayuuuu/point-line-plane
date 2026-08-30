from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    quota: dict[str, Any]
    created_at: datetime


class InviteLoginRequest(BaseModel):
    invite_code: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("invite_code", "display_name")
    @classmethod
    def strip_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class AuthResponse(BaseModel):
    user: UserResponse


class CodexAccountResponse(BaseModel):
    email: str
    plan_type: str | None = None
    display_name: str | None = None


class CodexLoginResponse(BaseModel):
    attempt_id: str
    status: Literal["pending", "authenticated", "failed"]
    auth_url: str | None = None
    account: CodexAccountResponse | None = None
    error: str | None = None


class OkResponse(BaseModel):
    ok: bool = True


class BetaInviteCreateRequest(BaseModel):
    code: SecretStr = Field(min_length=12, max_length=200)
    label: str = Field(min_length=1, max_length=120)
    max_uses: int = Field(default=1, ge=1, le=1_000)
    expires_at: datetime | None = None


class BetaInviteResponse(BaseModel):
    id: str
    label: str
    status: str
    max_uses: int
    use_count: int
    expires_at: datetime | None
    created_at: datetime


class BackupCreateRequest(BaseModel):
    confirm: bool


class BackupResponse(BaseModel):
    id: str
    mode: str
    status: str
    storage_ref: str
    sha256: str | None
    size_bytes: int
    evidence: dict[str, Any]
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None


class OperationsMetricsResponse(BaseModel):
    database: dict[str, Any]
    counts: dict[str, int]
    recent_failures: dict[str, int]
    generated_at: datetime


class ModelCredentialCreateRequest(BaseModel):
    provider: Literal["openai_compatible"] = "openai_compatible"
    api_key: SecretStr = Field(min_length=8, max_length=1_000)
    scope: Literal["development", "runtime", "both"] = "both"
    project_id: str | None = Field(default=None, max_length=36)
    expires_at: datetime | None = None


class ModelCredentialResponse(BaseModel):
    id: str
    project_id: str | None
    provider: str
    model: str
    scope: str
    masked_hint: str
    status: str
    expires_at: datetime | None
    verified_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ModelCredentialListResponse(BaseModel):
    items: list[ModelCredentialResponse]


class CredentialVerifyRequest(BaseModel):
    confirm_test_charge: bool


class CredentialRevokeRequest(BaseModel):
    confirm: bool


class CloudCredentialCreateRequest(BaseModel):
    provider: Literal["volcano_engine"] = "volcano_engine"
    access_key_id: SecretStr = Field(min_length=8, max_length=300)
    secret_access_key: SecretStr = Field(min_length=8, max_length=1_000)
    project_id: str
    expires_at: datetime | None = None


class CloudCredentialResponse(BaseModel):
    id: str
    project_id: str
    provider: str
    service: str
    scope: str
    masked_access_key: str
    status: str
    expires_at: datetime | None
    created_at: datetime


class CloudCredentialListResponse(BaseModel):
    items: list[CloudCredentialResponse]


class PlatformCapabilitiesResponse(BaseModel):
    ai_provider_mode: Literal["mock", "unverified", "verified"]
    ai_provider: str
    ai_model: str
    generated_execution_mode: str
    deployment_enabled: bool
    deployment_mode: Literal["mock", "external"]
    deployment_provider: str
    deployment_region: str
    github_sync_mode: Literal["mock", "external"]


class QuotaResponse(BaseModel):
    plan: str
    granted_units: int
    consumed_units: int
    reserved_units: int
    remaining_units: int


class UsageLedgerResponse(BaseModel):
    id: str
    project_id: str | None
    task_id: str | None
    credential_ref_id: str | None
    operation: str
    provider: str
    model: str
    source: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    quota_units: int
    estimated_cost_microusd: int
    pricing_configured: bool
    status: str
    trace_id: str
    created_at: datetime


class UsageLedgerListResponse(BaseModel):
    items: list[UsageLedgerResponse]


class UsageSummaryResponse(BaseModel):
    quota: QuotaResponse
    total_tokens: int
    platform_quota_units: int
    estimated_cost_microusd: int
    pricing_configured: bool


class CostQuoteRequest(BaseModel):
    operation: Literal[
        "requirements_prd",
        "solution",
        "development",
        "repair",
        "preview_run",
        "credential_verify",
    ]
    credential_id: str | None = Field(default=None, max_length=36)


class CostAuthorizationResponse(BaseModel):
    id: str
    project_id: str
    credential_ref_id: str | None
    operation: str
    provider: str
    model: str
    source: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_quota_units: int
    estimated_cost_microusd: int
    pricing_configured: bool
    requires_confirmation: bool
    status: str
    expires_at: datetime
    confirmed_at: datetime | None
    consumed_at: datetime | None
    created_at: datetime


class PreviewAcceptanceRequest(BaseModel):
    core_flow_works: bool
    result_is_useful: bool
    history_persists: bool
    errors_are_understandable: bool


class PreviewAcceptanceResponse(BaseModel):
    id: str
    project_id: str
    preview_id: str
    code_version_id: str
    decision: str
    checklist: dict[str, bool]
    created_at: datetime


class DeploymentAuthorizationRequest(BaseModel):
    credential_id: str
    action: Literal["deploy", "rollback"] = "deploy"
    target_deployment_id: str | None = None
    region: str = Field(default="cn-beijing", min_length=2, max_length=60)
    environment: Literal["production"] = "production"

    @model_validator(mode="after")
    def rollback_requires_target(self) -> DeploymentAuthorizationRequest:
        if self.action == "rollback" and not self.target_deployment_id:
            raise ValueError("回滚授权必须绑定目标部署")
        if self.action == "deploy" and self.target_deployment_id:
            raise ValueError("首次部署授权不能绑定回滚目标")
        return self


class DeploymentAuthorizationResponse(BaseModel):
    id: str
    project_id: str
    credential_ref_id: str
    action: str
    target_deployment_id: str | None
    provider: str
    region: str
    environment: str
    permission_scope: dict[str, Any]
    estimated_cost: dict[str, Any]
    status: str
    expires_at: datetime
    confirmed_at: datetime | None
    consumed_at: datetime | None
    created_at: datetime


class DeploymentAuthorizationListResponse(BaseModel):
    items: list[DeploymentAuthorizationResponse]


class DeploymentStartRequest(BaseModel):
    authorization_id: str


class DeploymentRollbackRequest(BaseModel):
    authorization_id: str
    confirm: bool


class DeploymentEventResponse(BaseModel):
    sequence: int
    type: str
    message: str
    payload: dict[str, Any]
    created_at: datetime


class DeploymentResponse(BaseModel):
    id: str
    project_id: str
    preview_id: str
    code_version_id: str
    authorization_id: str
    previous_deployment_id: str | None
    revision: int
    kind: str
    provider: str
    region: str
    environment: str
    status: str
    provider_ref: str | None
    deployment_url: str | None
    checkpoint: dict[str, Any]
    evidence: dict[str, Any]
    attempts: int
    error_code: str | None
    trace_id: str
    deployed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    events: list[DeploymentEventResponse]


class DeploymentListResponse(BaseModel):
    items: list[DeploymentResponse]


class DeliveryPackageCreateRequest(BaseModel):
    deployment_id: str
    confirm: bool


class DeliveryPackageResponse(BaseModel):
    id: str
    project_id: str
    deployment_id: str
    code_version_id: str
    revision: int
    status: str
    filename: str
    sha256: str
    size_bytes: int
    manifest: dict[str, Any]
    download_url: str
    created_at: datetime


class DeliveryPackageListResponse(BaseModel):
    items: list[DeliveryPackageResponse]


class GithubSyncRequest(BaseModel):
    repository_full_name: str = Field(
        min_length=3, max_length=200, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
    )
    branch: str = Field(default="main", min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._/-]+$")
    confirm: bool


class GithubSyncResponse(BaseModel):
    id: str
    project_id: str
    delivery_package_id: str
    repository_full_name: str
    branch: str
    status: str
    provider_ref: str | None
    repository_url: str | None
    evidence: dict[str, Any]
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class DevelopmentStartRequest(BaseModel):
    credential_id: str | None = Field(default=None, max_length=36)
    cost_authorization_id: str | None = Field(default=None, max_length=36)
    ui_style_key: Literal[
        "slack-aubergine",
        "pirsch-paper",
        "aira-editorial",
        "atlassian-confetti",
        "ameba-midnight",
        "sprout-contrast",
        "surfshark-coastal",
        "pop-typographic",
    ] = "pirsch-paper"

    @model_validator(mode="after")
    def require_matching_authorization(self) -> DevelopmentStartRequest:
        if self.credential_id and not self.cost_authorization_id:
            raise ValueError("使用用户模型凭证时必须同时提交费用确认")
        return self


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    idea: str = Field(min_length=3, max_length=10_000)

    @field_validator("name", "idea")
    @classmethod
    def strip_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class ProjectSummary(BaseModel):
    id: str
    name: str
    idea: str
    stage: str
    status: str
    scope: str
    current_artifact_version: int
    task_status: str | None = None
    task_progress: int | None = None
    preview_token: str | None = None
    created_at: datetime
    updated_at: datetime


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    type: str
    version: int
    status: str
    content: dict[str, Any]
    created_at: datetime


class ConfirmationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    type: str
    artifact_id: str
    decision: str
    comment: str | None
    created_at: datetime


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    stage: str
    status: str
    progress: int
    attempts: int
    max_attempts: int
    checkpoint: dict[str, Any]
    trace_id: str
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class PreviewSummary(BaseModel):
    id: str
    token: str
    status: str
    url_path: str
    code_version: int
    expires_at: datetime


class Question(BaseModel):
    id: str
    label: str
    reason: str
    required: bool = True


class NextAction(BaseModel):
    code: str
    message: str
    questions: list[Question] = Field(default_factory=list)


class ProjectDetail(ProjectSummary):
    latest_artifacts: list[ArtifactResponse] = Field(default_factory=list)
    confirmations: list[ConfirmationResponse] = Field(default_factory=list)
    active_task: TaskResponse | None = None
    preview: PreviewSummary | None = None
    preview_accepted: bool = False
    next_action: NextAction


class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]


class RequirementMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    question_id: str | None = Field(default=None, min_length=1, max_length=80)
    model: Literal["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.5"] | None = None
    reasoning_effort: Literal["low", "medium", "high", "xhigh"] | None = None
    progress_id: str | None = Field(
        default=None,
        min_length=8,
        max_length=80,
        pattern=r"^[A-Za-z0-9-]+$",
    )

    @field_validator("message", "question_id", "progress_id", "model", "reasoning_effort")
    @classmethod
    def strip_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("消息不能为空")
        return value


class CodexReasoningProgressResponse(BaseModel):
    status: Literal["pending", "running", "completed", "failed"]
    summary: str


class RequirementResponse(BaseModel):
    project: ProjectDetail
    status: Literal["question", "prd_ready"]
    reply: str
    questions: list[Question] = Field(default_factory=list)
    artifact: ArtifactResponse | None = None


class CodexConversationMessage(BaseModel):
    id: str
    role: Literal["assistant", "user"]
    content: str


class CodexClarifyingQuestion(BaseModel):
    mode: Literal["single", "multiple"]
    prompt: str
    options: list[str] = Field(default_factory=list)


class CodexConversationResponse(BaseModel):
    project: ProjectDetail
    conversation_id: str
    title: str
    thread_id: str | None = None
    messages: list[CodexConversationMessage] = Field(default_factory=list)
    draft: dict[str, Any] | None = None
    current_question: CodexClarifyingQuestion | None = None


class CodexConversationSummary(BaseModel):
    id: str
    title: str
    active: bool = False
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class CodexConversationListResponse(BaseModel):
    items: list[CodexConversationSummary] = Field(default_factory=list)


class CodexRequirementResponse(CodexConversationResponse):
    status: Literal["question", "prd_ready"]
    reply: str
    current_question: CodexClarifyingQuestion | None = None
    artifact: ArtifactResponse | None = None


class ArtifactListResponse(BaseModel):
    items: list[ArtifactResponse]


class ConfirmationRequest(BaseModel):
    artifact_id: str = Field(min_length=1, max_length=80)
    decision: Literal["confirm", "revise"]
    comment: str | None = Field(default=None, max_length=5_000)

    @model_validator(mode="after")
    def revision_needs_comment(self) -> ConfirmationRequest:
        if self.decision == "revise" and not (self.comment and self.comment.strip()):
            raise ValueError("提出修改时必须填写修改意见")
        if self.comment is not None:
            self.comment = self.comment.strip() or None
        return self


class ConfirmationActionResponse(BaseModel):
    project: ProjectDetail
    artifact: ArtifactResponse
    confirmation: ConfirmationResponse | None = None
    next_artifact: ArtifactResponse | None = None


class TaskEventResponse(BaseModel):
    id: str
    task_id: str
    sequence: int
    type: str
    message: str
    payload: dict[str, Any]
    created_at: datetime


class CodeVersionResponse(BaseModel):
    id: str
    project_id: str
    version: int
    commit_ref: str
    test_status: str
    manifest: dict[str, Any]
    created_at: datetime


class PreviewConfig(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    input_label: str = Field(min_length=1, max_length=100)
    input_placeholder: str = Field(min_length=1, max_length=200)
    submit_label: str = Field(min_length=1, max_length=60)
    output_title: str = Field(min_length=1, max_length=100)
    template: Literal[
        "controlled_text_agent_v1",
        "controlled_html_webapp_v1",
    ] = "controlled_text_agent_v1"


class AgentResult(BaseModel):
    summary: str = Field(min_length=1, max_length=4_000)
    key_points: list[str] = Field(min_length=1, max_length=8)
    next_step: str = Field(min_length=1, max_length=1_000)


class PreviewRunResponse(BaseModel):
    id: str
    input: str
    result: AgentResult
    provider: str
    model: str
    provider_verification: Literal["mock", "unverified", "verified"]
    usage: dict[str, Any]
    latency_ms: float
    created_at: datetime


class PreviewResponse(BaseModel):
    id: str
    token: str
    project_id: str
    status: str
    url_path: str
    expires_at: datetime
    code_version: CodeVersionResponse
    config: PreviewConfig
    history: list[PreviewRunResponse]


class PreviewRunRequest(BaseModel):
    input: str = Field(min_length=1, max_length=5_000)
    credential_id: str | None = Field(default=None, max_length=36)
    cost_authorization_id: str | None = Field(default=None, max_length=36)

    @field_validator("input")
    @classmethod
    def strip_input(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("输入不能为空")
        return value

    @model_validator(mode="after")
    def require_live_cost_authorization(self) -> PreviewRunRequest:
        if self.credential_id and not self.cost_authorization_id:
            raise ValueError("使用用户模型凭证时必须同时提交费用确认")
        return self


class PreviewFeedbackRequest(BaseModel):
    feedback: str = Field(min_length=1, max_length=5_000)

    @field_validator("feedback")
    @classmethod
    def strip_feedback(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("反馈不能为空")
        return value


class FeedbackResponse(BaseModel):
    classification: Literal["in_scope", "new_scope"]
    reason: str
    next_stage: str
    project: ProjectDetail
    solution_artifact: ArtifactResponse | None = None
    change_request_artifact: ArtifactResponse | None = None


class CostItem(BaseModel):
    item: str
    estimate: str
    note: str


class PrdFailureStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str
    fallback: str


class PrdSuccessMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    target: str
    measurement: str


class PrdHarness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tools: list[str]
    knowledge: list[str]
    observation: list[str]
    actions: list[str]
    permissions: list[str]


class PrdBlueprintComponentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component: str
    decision: Literal["selected", "not_selected", "pending"]
    reason: str
    production_notes: str
    reference: str


class PrdBlueprintArchitectureLayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: int = Field(ge=1, le=7)
    name: str
    responsibilities: list[str]
    implementation_anchors: list[str]


class PrdBlueprintToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    purpose: str
    input: str
    output: str
    side_effect: str
    permission: str
    layer: str


class PrdBlueprintCodePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skeleton: list[str]
    hardening: list[str]
    productization: list[str]
    confirmation_gate: str


class PrdBlueprintProcess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blueprint_source: str
    component_selection: list[PrdBlueprintComponentDecision]
    layered_architecture: list[PrdBlueprintArchitectureLayer]
    cross_layer_data_flow: list[str]
    tool_catalog: list[PrdBlueprintToolSpec]
    system_prompt_draft: str
    context_and_memory_strategy: list[str]
    security_and_permissions: list[str]
    observability: list[str]
    technology_and_deployment: list[str]
    code_generation_plan: PrdBlueprintCodePlan


# Fixed artifact contract: the top-level PRD fields are the concise white-box
# confirmation layer; full_document is the canonical document consumed by
# preview and every downstream stage. Other artifact types should use the same
# two-layer contract rather than rebuilding a "full" preview from their summary.
class PrdFullDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_goal: str
    success_definition: str
    usage_context: list[str]
    interaction_model: str
    inputs: list[str]
    end_to_end_loop: list[str]
    deliverables: list[str]
    functional_requirements: list[str]
    non_functional_requirements: list[str]
    external_actions: list[str]
    domain_knowledge: list[str]
    data_and_state: list[str]
    boundaries: list[str]
    constraints: list[str]
    failure_strategies: list[PrdFailureStrategy]
    success_metrics: list[PrdSuccessMetric]
    harness: PrdHarness
    open_questions: list[str]
    traceability: list[str]
    blueprint_process: PrdBlueprintProcess | None = None


def _backfill_blueprint_process(document: PrdFullDocument) -> PrdBlueprintProcess:
    layer_names = [
        "交互层",
        "产品层",
        "Agent 编排层",
        "模型层",
        "能力集成层",
        "数据层",
        "基础设施层",
    ]
    tools = document.harness.tools or ["待确认"]
    return PrdBlueprintProcess(
        blueprint_source="agent-blueprint/BLUEPRINT.md",
        component_selection=[
            PrdBlueprintComponentDecision(
                component="蓝图组件选型",
                decision="pending",
                reason="该历史制品生成时尚未保存组件选型结果，需在生成新版时按 PRD 特征逐项判断",
                production_notes="只选必要组件；每项都要说明没有它会产生什么影响",
                reference="s01-s17 待匹配",
            )
        ],
        layered_architecture=[
            PrdBlueprintArchitectureLayer(
                layer=index,
                name=name,
                responsibilities=["待确认"],
                implementation_anchors=["生成新版完整 PRD 时按蓝图补齐"],
            )
            for index, name in enumerate(layer_names, start=1)
        ],
        cross_layer_data_flow=document.end_to_end_loop or ["待确认"],
        tool_catalog=[
            PrdBlueprintToolSpec(
                name=tool,
                purpose="待确认",
                input="待确认",
                output="待确认",
                side_effect="待确认",
                permission="待确认",
                layer="能力集成层",
            )
            for tool in tools
        ],
        system_prompt_draft="待确认；仅当产品需要模型能力时，按身份、规则、工具说明和知识目录生成",
        context_and_memory_strategy=document.data_and_state or ["待确认"],
        security_and_permissions=[*document.boundaries, *document.harness.permissions]
        or ["待确认"],
        observability=document.harness.observation or ["待确认"],
        technology_and_deployment=["技术栈、运行形态与部署环境待方案确认"],
        code_generation_plan=PrdBlueprintCodePlan(
            skeleton=["PRD 与方案确认后生成可运行骨架"],
            hardening=["骨架确认后补齐错误处理、超时、重试、日志、配置和权限检查"],
            productization=["硬化后再完成组件集成、测试、部署脚本和 README"],
            confirmation_gate="先确认 PRD，再确认架构方案；方案确认前不生成产品代码",
        ),
    )


class PrdContent(BaseModel):
    title: str
    summary: str
    target_users: list[str]
    problem: str
    core_flow: list[str]
    features: list[str]
    scope: dict[str, list[str]]
    acceptance_criteria: list[str]
    assumptions: list[str]
    source_notes: list[str]
    revision_notes: list[str] = Field(default_factory=list)
    full_document: PrdFullDocument | None = None
    generation: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def backfill_full_document(self) -> PrdContent:
        if self.full_document is not None:
            if self.full_document.blueprint_process is None:
                self.full_document.blueprint_process = _backfill_blueprint_process(
                    self.full_document
                )
            return self

        external_actions = [
            item
            for item in self.features
            if any(
                term in item
                for term in ("通知", "声音", "接口", "API", "上传", "下载", "发送", "调用")
            )
        ]
        data_and_state = [
            item
            for item in self.features
            if any(term in item for term in ("保存", "记录", "统计", "历史", "状态", "数据"))
        ]
        open_questions = [
            item for item in [*self.assumptions, *self.source_notes] if "待确认" in item
        ]
        self.full_document = PrdFullDocument(
            product_goal=self.summary,
            success_definition=(
                f"满足全部 {len(self.acceptance_criteria)} 项完成标准"
                if self.acceptance_criteria
                else "待确认"
            ),
            usage_context=[*self.target_users, "使用频率：待确认"],
            interaction_model="同步或异步方式待确认",
            inputs=["用户输入与操作字段待产品方案确认"],
            end_to_end_loop=self.core_flow or ["待确认"],
            deliverables=[self.title, "可供后续方案、生成与部署流程读取的版本化需求制品"],
            functional_requirements=self.features or ["待确认"],
            non_functional_requirements=self.acceptance_criteria or ["待确认"],
            external_actions=external_actions or ["无外部动作或待确认"],
            domain_knowledge=self.source_notes or ["待确认"],
            data_and_state=data_and_state or ["待确认"],
            boundaries=self.scope.get("excluded", []) or ["待确认"],
            constraints=self.assumptions or ["待确认"],
            failure_strategies=[
                PrdFailureStrategy(
                    scenario="核心流程、外部动作或持久化失败",
                    fallback="停止当前动作、保留用户输入与可恢复状态，并展示可理解的重试提示",
                )
            ],
            success_metrics=[
                PrdSuccessMetric(
                    metric=f"完成标准 {index + 1}",
                    target=item,
                    measurement="按对应验收用例测试并记录结果",
                )
                for index, item in enumerate(self.acceptance_criteria)
            ]
            or [PrdSuccessMetric(metric="核心目标达成率", target="待确认", measurement="待确认")],
            harness={
                "tools": external_actions or ["无 / N/A"],
                "knowledge": self.source_notes or ["待确认"],
                "observation": self.acceptance_criteria or ["待确认"],
                "actions": self.core_flow or ["待确认"],
                "permissions": self.scope.get("excluded", []) or ["待确认"],
            },
            open_questions=open_questions or ["使用频率、交互方式与非功能约束待方案阶段复核"],
            traceability=self.source_notes or ["待确认"],
        )
        self.full_document.blueprint_process = _backfill_blueprint_process(self.full_document)
        return self


class SolutionContent(BaseModel):
    title: str
    summary: str
    recommended_approach: str
    product_scope: list[str]
    deferred: list[str]
    user_costs: list[CostItem]
    external_accounts: list[str]
    risks: list[str]
    deliverables: list[str]
    architecture: dict[str, Any]
    revision_notes: list[str] = Field(default_factory=list)
    generation: dict[str, Any] = Field(default_factory=dict)


class FailureReportContent(BaseModel):
    title: str
    task_id: str
    failed_stage: str
    attempts: int
    error_code: str
    last_checkpoint: dict[str, Any]
    attempted_recovery: list[str]
    recovery: str


class ChangeRequestContent(BaseModel):
    title: str
    feedback: str
    classification: Literal["in_scope"]
    reason: str
    source_preview_id: str | None = None
    source_code_version_id: str | None = None


class JourneyNodeResponse(BaseModel):
    id: str
    graph_id: str
    key: str
    position: int
    node_type: str
    status: str
    title: str
    caption: str
    product_purpose: str
    user_sees: str
    system_does: str
    technical_contract: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProductGraphResponse(BaseModel):
    id: str
    project_id: str
    version: int
    status: str
    title: str
    product_goal: str
    source_artifact_id: str | None
    base_code_version_id: str | None
    nodes: list[JourneyNodeResponse]
    created_at: datetime
    updated_at: datetime


class DecisionOptionResponse(BaseModel):
    id: str
    key: str
    position: int
    title: str
    description: str
    recommended: bool
    product_impact: dict[str, Any]
    technical_effects: dict[str, Any]


class ProductDecisionResponse(BaseModel):
    id: str
    project_id: str
    graph_id: str
    node_id: str
    key: str
    status: str
    title: str
    question: str
    selected_option_key: str | None
    options: list[DecisionOptionResponse]
    confirmed_at: datetime | None
    created_at: datetime


class DecisionCenterResponse(BaseModel):
    project_id: str
    graph_id: str
    open_count: int
    confirmed_count: int
    items: list[ProductDecisionResponse]


class ConfirmProductDecisionRequest(BaseModel):
    option_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_\-]+$")
    idempotency_key: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._\-]+$")


class ProductChangeRequestResponse(BaseModel):
    id: str
    project_id: str
    graph_id: str
    node_id: str | None
    source_type: str
    source_id: str
    status: str
    scope_classification: str
    product_request: str
    product_impact: dict[str, Any]
    technical_context: dict[str, Any]
    base_artifact_id: str | None
    base_code_version_id: str | None
    confirmed_at: datetime | None
    created_at: datetime


class ProductDecisionActionResponse(BaseModel):
    decision: ProductDecisionResponse
    change_request: ProductChangeRequestResponse
    next_action: NextAction


class SimulationStartRequest(BaseModel):
    persona_key: Literal["first_time_non_technical_user"] = "first_time_non_technical_user"
    idempotency_key: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._\-]+$")


class SimulationStepResponse(BaseModel):
    id: str
    run_id: str
    node_id: str
    node_key: str
    node_title: str
    sequence: int
    status: str
    observation: str
    technical_evidence: dict[str, Any]
    duration_ms: int
    created_at: datetime


class FrictionFindingResponse(BaseModel):
    id: str
    run_id: str
    node_id: str
    node_key: str
    severity: str
    status: str
    product_summary: str
    evidence: dict[str, Any]
    resolution_key: str | None
    resolution_options: list[dict[str, Any]]
    resolved_at: datetime | None
    created_at: datetime


class SimulationRunResponse(BaseModel):
    id: str
    project_id: str
    graph_id: str
    persona_key: str
    persona_name: str
    status: str
    current_node_id: str | None
    checkpoint: dict[str, Any]
    steps: list[SimulationStepResponse]
    findings: list[FrictionFindingResponse]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResolveFindingRequest(BaseModel):
    resolution_key: Literal["add_input_example", "explain_before_input"]
    idempotency_key: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._\-]+$")


class FindingResolutionResponse(BaseModel):
    finding: FrictionFindingResponse
    simulation: SimulationRunResponse
    change_request: ProductChangeRequestResponse


class ProductDashboardResponse(BaseModel):
    project_id: str
    graph: ProductGraphResponse
    decision_center: DecisionCenterResponse
    latest_simulation: SimulationRunResponse | None
    open_findings: list[FrictionFindingResponse]
    queued_changes: list[ProductChangeRequestResponse]
    next_action: NextAction


class GeneratedCodeFile(BaseModel):
    path: str = Field(min_length=1, max_length=240)
    language: str = Field(min_length=1, max_length=40)
    product_purpose: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=100_000)


class CodingBundle(BaseModel):
    template: Literal[
        "controlled_text_agent_backend_v1",
        "controlled_html_webapp_v1",
    ] = "controlled_text_agent_backend_v1"
    summary: str = Field(min_length=1, max_length=500)
    files: list[GeneratedCodeFile] = Field(min_length=6, max_length=24)
    run_instructions: list[str] = Field(min_length=1, max_length=8)
    generation: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def paths_are_unique(self) -> CodingBundle:
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("生成文件路径不能重复")
        return self


class CodeFileMetadataResponse(BaseModel):
    id: str
    path: str
    language: str
    product_purpose: str
    sha256: str
    size_bytes: int
    created_at: datetime


class CodeFileContentResponse(CodeFileMetadataResponse):
    commit_ref: str
    content: str


class ToolExecutionResponse(BaseModel):
    id: str
    sequence: int
    tool_name: str
    side_effect: str
    status: str
    input_summary: dict[str, Any]
    output_summary: dict[str, Any]
    error_code: str | None
    started_at: datetime
    completed_at: datetime | None


class DevelopmentWorkspaceResponse(BaseModel):
    id: str
    project_id: str
    runtime_type: str
    status: str
    current_commit_ref: str | None
    file_count: int
    size_bytes: int
    created_at: datetime
    updated_at: datetime


class DevelopmentRunResponse(BaseModel):
    id: str
    project_id: str
    workspace_id: str
    task_id: str
    solution_artifact_id: str
    code_version_id: str | None
    resumed_from_run_id: str | None
    status: str
    current_step: str
    provider: str | None
    model: str | None
    provider_verification: str | None
    plan: dict[str, Any]
    budget: dict[str, Any]
    context: dict[str, Any]
    usage: dict[str, Any]
    error_code: str | None
    tools: list[ToolExecutionResponse]
    files: list[CodeFileMetadataResponse]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class DevelopmentRunListResponse(BaseModel):
    items: list[DevelopmentRunResponse]


class QualityRunResponse(BaseModel):
    id: str
    project_id: str
    task_id: str
    development_run_id: str
    code_version_id: str
    sequence: int
    kind: Literal["compile", "pytest", "runtime_smoke"]
    status: Literal["running", "passed", "failed", "timed_out"]
    attempt: int
    duration_ms: float
    exit_code: int | None
    summary: dict[str, Any]
    output_excerpt: str
    started_at: datetime
    completed_at: datetime | None


class RepairAttemptResponse(BaseModel):
    id: str
    project_id: str
    task_id: str
    development_run_id: str
    attempt: int
    status: Literal["running", "succeeded", "failed"]
    source_code_version_id: str
    repaired_code_version_id: str | None
    failure_summary: dict[str, Any]
    strategy_summary: str
    usage: dict[str, Any]
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None


class QualityHistoryResponse(BaseModel):
    quality_runs: list[QualityRunResponse]
    repair_attempts: list[RepairAttemptResponse]


class PreviewRuntimeResponse(BaseModel):
    id: str
    preview_id: str
    project_id: str
    code_version_id: str
    runtime_type: str
    status: Literal["provisioning", "ready", "failed", "stopped", "expired"]
    base_url: str | None
    health: dict[str, Any]
    error_code: str | None
    started_at: datetime | None
    last_health_at: datetime | None
    stopped_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RuntimeAnalyzeResponse(BaseModel):
    result: AgentResult
    history_count: int


class RuntimeHistoryResponse(BaseModel):
    items: list[dict[str, Any]]
