from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found
from app.models import (
    Artifact,
    CodeVersion,
    DecisionOption,
    FrictionFinding,
    JourneyNode,
    ProductChangeRequest,
    ProductDecision,
    ProductGraph,
    Project,
    SimulationRun,
    SimulationStep,
)
from app.models.enums import (
    ArtifactStatus,
    ArtifactType,
    ChangeRequestSource,
    ChangeRequestStatus,
    DecisionStatus,
    FindingSeverity,
    FindingStatus,
    JourneyNodeStatus,
    JourneyNodeType,
    ProductGraphStatus,
    ScopeClassification,
    SimulationStatus,
    SimulationStepStatus,
)
from app.schemas.contracts import (
    DecisionCenterResponse,
    DecisionOptionResponse,
    FrictionFindingResponse,
    JourneyNodeResponse,
    NextAction,
    ProductChangeRequestResponse,
    ProductDashboardResponse,
    ProductDecisionResponse,
    ProductGraphResponse,
    SimulationRunResponse,
    SimulationStepResponse,
)

SUPPORTED_PERSONAS = {
    "first_time_non_technical_user": "第一次使用的非技术用户",
}

FINDING_RESOLUTIONS: list[dict[str, Any]] = [
    {
        "key": "add_input_example",
        "title": "补一条真实输入示例",
        "description": "让用户不用猜应该写多长、写什么内容。",
        "recommended": True,
        "technical_effects": {
            "frontend_component": "InputPanel",
            "change": "render_example_prompt",
            "api_contract": "unchanged",
        },
    },
    {
        "key": "explain_before_input",
        "title": "输入前增加一句说明",
        "description": "先解释系统会如何使用这段内容，再让用户开始。",
        "recommended": False,
        "technical_effects": {
            "frontend_component": "InputPanel",
            "change": "render_pre_input_explanation",
            "api_contract": "unchanged",
        },
    },
]


def _now() -> datetime:
    return datetime.now(UTC)


def _scoped_key(prefix: str, object_id: str, user_key: str) -> str:
    digest = sha256(user_key.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{object_id}:{digest}"


def _latest_source_artifact(db: Session, project_id: str) -> Artifact | None:
    return db.scalar(
        select(Artifact)
        .where(
            Artifact.project_id == project_id,
            Artifact.type.in_([ArtifactType.SOLUTION.value, ArtifactType.PRD.value]),
            Artifact.status == ArtifactStatus.CONFIRMED.value,
        )
        .order_by(
            (Artifact.type == ArtifactType.SOLUTION.value).desc(),
            Artifact.created_at.desc(),
        )
        .limit(1)
    )


def _latest_code_version(db: Session, project_id: str) -> CodeVersion | None:
    return db.scalar(
        select(CodeVersion)
        .where(CodeVersion.project_id == project_id)
        .order_by(CodeVersion.version.desc())
        .limit(1)
    )


def active_graph(db: Session, project_id: str) -> ProductGraph | None:
    return db.scalar(
        select(ProductGraph)
        .where(
            ProductGraph.project_id == project_id,
            ProductGraph.status == ProductGraphStatus.ACTIVE.value,
        )
        .order_by(ProductGraph.version.desc())
        .limit(1)
    )


def require_active_graph(db: Session, project_id: str) -> ProductGraph:
    graph = active_graph(db, project_id)
    if not graph:
        raise ApiError(
            "PRODUCT_GRAPH_NOT_INITIALIZED",
            "还没有生成产品流程图，请先初始化第二阶段产品模型。",
            409,
        )
    return graph


def _node_seed() -> list[dict[str, Any]]:
    return [
        {
            "key": "target_user",
            "position": 0,
            "node_type": JourneyNodeType.PERSONA.value,
            "status": JourneyNodeStatus.READY.value,
            "title": "谁来使用",
            "caption": "第一次使用的非技术用户",
            "product_purpose": "先锁定真实使用者，后面的内容和操作才不会变成给所有人看的空话。",
            "user_sees": "页面用一句话说明这个产品帮助谁、解决什么问题。",
            "system_does": "读取项目目标和已确认产物，保持用户、问题与首版范围一致。",
            "technical_contract_json": {
                "domain_entity": "Project",
                "source_fields": ["projects.idea", "artifacts.content_json.target_users"],
                "api": "GET /api/v1/projects/{project_id}/product-dashboard",
            },
        },
        {
            "key": "input",
            "position": 1,
            "node_type": JourneyNodeType.INPUT.value,
            "status": JourneyNodeStatus.NEEDS_DECISION.value,
            "title": "用户交什么",
            "caption": "粘贴一段真实文本",
            "product_purpose": "让用户清楚第一步该做什么，并知道什么样的内容能得到好结果。",
            "user_sees": "一个有真实示例、边界说明和明确按钮的输入区。",
            "system_does": "校验非空文本和长度，再把受控输入交给预览运行接口。",
            "technical_contract_json": {
                "frontend_component": "InputPanel",
                "request_schema": "PreviewRunRequest",
                "api": "POST /api/v1/previews/{preview_token}/runs",
                "validation": {"min_length": 1, "max_length": 5000},
            },
        },
        {
            "key": "ai_analysis",
            "position": 2,
            "node_type": JourneyNodeType.AI_ACTION.value,
            "status": JourneyNodeStatus.READY.value,
            "title": "AI 做什么",
            "caption": "整理薄弱点并生成下一步",
            "product_purpose": "把模型能力翻译成用户可理解、可以判断好坏的一段过程。",
            "user_sees": "正在分析、失败重试和完成状态，不展示内部思考或原始堆栈。",
            "system_does": "通过统一 Provider 调用模型，校验结构化结果并记录用量与耗时。",
            "technical_contract_json": {
                "service": "app.services.providers.generate_with_retry",
                "output_schema": "AgentResult",
                "retry_policy": "AI_MAX_ATTEMPTS",
                "secret_boundary": "AI_API_KEY is backend-only",
            },
        },
        {
            "key": "result",
            "position": 3,
            "node_type": JourneyNodeType.OUTPUT.value,
            "status": JourneyNodeStatus.NEEDS_DECISION.value,
            "title": "用户得到什么",
            "caption": "摘要、关键点和明确下一步",
            "product_purpose": "让结果不只是模型的一段长回答，而是用户能检查、理解和继续行动的产物。",
            "user_sees": "分区卡片，同时保留复制、重试和反馈入口。",
            "system_does": "按 AgentResult 固定结构返回 summary、key_points 和 next_step。",
            "technical_contract_json": {
                "response_schema": "AgentResult",
                "fields": ["summary", "key_points", "next_step"],
                "history_entity": "PreviewRun",
            },
        },
        {
            "key": "history",
            "position": 4,
            "node_type": JourneyNodeType.PERSISTENCE.value,
            "status": JourneyNodeStatus.READY.value,
            "title": "如何继续使用",
            "caption": "刷新后仍能回看结果",
            "product_purpose": "让用户敢于关闭页面，知道工作和结果不会因为刷新而消失。",
            "user_sees": "历史记录、来源版本和最后更新时间。",
            "system_does": "把运行、模型标识、用量、耗时和版本关联持久化到数据库。",
            "technical_contract_json": {
                "database_entity": "PreviewRun",
                "foreign_key": "preview_runs.preview_id -> previews.id",
                "recovery": "database-backed",
            },
        },
    ]


def initialize_product_graph(db: Session, project: Project) -> tuple[ProductGraph, bool]:
    existing = active_graph(db, project.id)
    if existing:
        return existing, False

    current_version = db.scalar(
        select(func.max(ProductGraph.version)).where(ProductGraph.project_id == project.id)
    )
    artifact = _latest_source_artifact(db, project.id)
    code_version = _latest_code_version(db, project.id)
    graph = ProductGraph(
        project_id=project.id,
        version=int(current_version or 0) + 1,
        status=ProductGraphStatus.ACTIVE.value,
        title=f"{project.name}｜产品体验流程",
        product_goal=f"把“{project.idea}”变成用户看得懂、能逐步确认、可以恢复的产品体验。",
        source_artifact_id=artifact.id if artifact else None,
        base_code_version_id=code_version.id if code_version else None,
    )
    db.add(graph)
    db.flush()

    nodes: dict[str, JourneyNode] = {}
    for item in _node_seed():
        node = JourneyNode(graph_id=graph.id, **item)
        db.add(node)
        nodes[item["key"]] = node
    db.flush()

    decisions = [
        {
            "key": "input_guidance",
            "node": nodes["input"],
            "title": "第一次使用时，怎样让用户知道该输入什么？",
            "question": "这会影响首屏理解成本、页面复杂度和后续数据结构。",
            "options": [
                {
                    "key": "real_example",
                    "title": "直接给一条真实示例",
                    "description": "用户一眼就能照着写，首版成本最低。",
                    "recommended": True,
                    "product_impact": {"learning_cost": "low", "delivery_scope": "small", "risk": "low"},
                    "technical_effects": {
                        "frontend_component": "InputPanel",
                        "change": "add_example_prompt",
                        "api_contract": "unchanged",
                    },
                },
                {
                    "key": "guided_questions",
                    "title": "拆成三步引导",
                    "description": "更容易回答，但会增加页面状态和开发范围。",
                    "recommended": False,
                    "product_impact": {"learning_cost": "lowest", "delivery_scope": "medium", "risk": "medium"},
                    "technical_effects": {
                        "frontend_component": "GuidedInputWizard",
                        "change": "add_multi_step_state",
                        "api_contract": "requires_draft_state",
                    },
                },
                {
                    "key": "blank_input",
                    "title": "保持空白输入框",
                    "description": "页面最简，但新用户需要自己猜输入标准。",
                    "recommended": False,
                    "product_impact": {"learning_cost": "high", "delivery_scope": "none", "risk": "high"},
                    "technical_effects": {"frontend_component": "InputPanel", "change": "none", "api_contract": "unchanged"},
                },
            ],
        },
        {
            "key": "result_structure",
            "node": nodes["result"],
            "title": "AI 结果应该怎样呈现，用户才容易判断？",
            "question": "技术字段保持不变，选择只决定怎样把它翻译成大众能理解的界面。",
            "options": [
                {
                    "key": "visual_cards",
                    "title": "按任务分成三张卡片",
                    "description": "摘要、薄弱点、下一步各自独立，最容易扫描。",
                    "recommended": True,
                    "product_impact": {"readability": "high", "delivery_scope": "small", "risk": "low"},
                    "technical_effects": {
                        "response_schema": "AgentResult",
                        "mapping": {"summary": "SummaryCard", "key_points": "InsightList", "next_step": "NextStepCard"},
                        "api_contract": "unchanged",
                    },
                },
                {
                    "key": "single_report",
                    "title": "合成一份完整报告",
                    "description": "内容连续，但重点更难快速定位。",
                    "recommended": False,
                    "product_impact": {"readability": "medium", "delivery_scope": "small", "risk": "medium"},
                    "technical_effects": {"response_schema": "AgentResult", "mapping": "ReportView", "api_contract": "unchanged"},
                },
            ],
        },
    ]
    for decision_seed in decisions:
        decision = ProductDecision(
            project_id=project.id,
            graph_id=graph.id,
            node_id=decision_seed["node"].id,
            key=decision_seed["key"],
            status=DecisionStatus.OPEN.value,
            title=decision_seed["title"],
            question=decision_seed["question"],
        )
        db.add(decision)
        db.flush()
        for position, option_seed in enumerate(decision_seed["options"]):
            db.add(
                DecisionOption(
                    decision_id=decision.id,
                    position=position,
                    key=option_seed["key"],
                    title=option_seed["title"],
                    description=option_seed["description"],
                    recommended=option_seed["recommended"],
                    product_impact_json=option_seed["product_impact"],
                    technical_effects_json=option_seed["technical_effects"],
                )
            )
    db.flush()
    return graph, True


def graph_response(db: Session, graph: ProductGraph) -> ProductGraphResponse:
    nodes = list(
        db.scalars(
            select(JourneyNode)
            .where(JourneyNode.graph_id == graph.id)
            .order_by(JourneyNode.position)
        )
    )
    return ProductGraphResponse(
        id=graph.id,
        project_id=graph.project_id,
        version=graph.version,
        status=graph.status,
        title=graph.title,
        product_goal=graph.product_goal,
        source_artifact_id=graph.source_artifact_id,
        base_code_version_id=graph.base_code_version_id,
        nodes=[
            JourneyNodeResponse(
                id=node.id,
                graph_id=node.graph_id,
                key=node.key,
                position=node.position,
                node_type=node.node_type,
                status=node.status,
                title=node.title,
                caption=node.caption,
                product_purpose=node.product_purpose,
                user_sees=node.user_sees,
                system_does=node.system_does,
                technical_contract=node.technical_contract_json,
                created_at=node.created_at,
                updated_at=node.updated_at,
            )
            for node in nodes
        ],
        created_at=graph.created_at,
        updated_at=graph.updated_at,
    )


def decision_response(db: Session, decision: ProductDecision) -> ProductDecisionResponse:
    options = list(
        db.scalars(
            select(DecisionOption)
            .where(DecisionOption.decision_id == decision.id)
            .order_by(DecisionOption.position)
        )
    )
    return ProductDecisionResponse(
        id=decision.id,
        project_id=decision.project_id,
        graph_id=decision.graph_id,
        node_id=decision.node_id,
        key=decision.key,
        status=decision.status,
        title=decision.title,
        question=decision.question,
        selected_option_key=decision.selected_option_key,
        options=[
            DecisionOptionResponse(
                id=option.id,
                key=option.key,
                position=option.position,
                title=option.title,
                description=option.description,
                recommended=option.recommended,
                product_impact=option.product_impact_json,
                technical_effects=option.technical_effects_json,
            )
            for option in options
        ],
        confirmed_at=decision.confirmed_at,
        created_at=decision.created_at,
    )


def decision_center_response(db: Session, graph: ProductGraph) -> DecisionCenterResponse:
    decisions = list(
        db.scalars(
            select(ProductDecision)
            .where(ProductDecision.graph_id == graph.id)
            .order_by(ProductDecision.created_at, ProductDecision.id)
        )
    )
    return DecisionCenterResponse(
        project_id=graph.project_id,
        graph_id=graph.id,
        open_count=sum(item.status == DecisionStatus.OPEN.value for item in decisions),
        confirmed_count=sum(item.status == DecisionStatus.CONFIRMED.value for item in decisions),
        items=[decision_response(db, item) for item in decisions],
    )


def change_request_response(item: ProductChangeRequest) -> ProductChangeRequestResponse:
    return ProductChangeRequestResponse(
        id=item.id,
        project_id=item.project_id,
        graph_id=item.graph_id,
        node_id=item.node_id,
        source_type=item.source_type,
        source_id=item.source_id,
        status=item.status,
        scope_classification=item.scope_classification,
        product_request=item.product_request,
        product_impact=item.product_impact_json,
        technical_context=item.technical_context_json,
        base_artifact_id=item.base_artifact_id,
        base_code_version_id=item.base_code_version_id,
        confirmed_at=item.confirmed_at,
        created_at=item.created_at,
    )


def confirm_product_decision(
    db: Session,
    *,
    decision: ProductDecision,
    option_key: str,
    idempotency_key: str,
) -> tuple[ProductDecision, ProductChangeRequest]:
    scoped_key = _scoped_key("decision", decision.id, idempotency_key)
    if decision.status == DecisionStatus.CONFIRMED.value:
        if decision.confirmation_key != scoped_key or decision.selected_option_key != option_key:
            raise ApiError("DECISION_ALREADY_CONFIRMED", "这个产品决策已经确认，不能重复改选。", 409)
        existing = db.scalar(
            select(ProductChangeRequest).where(ProductChangeRequest.idempotency_key == scoped_key)
        )
        if not existing:
            raise ApiError("DECISION_CHANGE_MISSING", "决策记录不完整，请联系管理员。", 500)
        return decision, existing

    option = db.scalar(
        select(DecisionOption).where(
            DecisionOption.decision_id == decision.id,
            DecisionOption.key == option_key,
        )
    )
    if not option:
        raise ApiError("DECISION_OPTION_NOT_FOUND", "所选方案不属于这个产品决策。", 422)

    node = db.get(JourneyNode, decision.node_id)
    if not node:
        raise not_found("产品流程节点")
    decision.status = DecisionStatus.CONFIRMED.value
    decision.selected_option_key = option.key
    decision.confirmation_key = scoped_key
    decision.confirmed_at = _now()
    node.status = JourneyNodeStatus.OPTIMIZED.value

    graph = db.get(ProductGraph, decision.graph_id)
    if not graph:
        raise not_found("产品流程图")
    change = ProductChangeRequest(
        project_id=decision.project_id,
        graph_id=decision.graph_id,
        node_id=decision.node_id,
        source_type=ChangeRequestSource.DECISION.value,
        source_id=decision.id,
        status=ChangeRequestStatus.CONFIRMED.value,
        scope_classification=ScopeClassification.IN_SCOPE.value,
        product_request=f"在“{node.title}”节点采用“{option.title}”。",
        product_impact_json=option.product_impact_json,
        technical_context_json=option.technical_effects_json,
        base_artifact_id=graph.source_artifact_id,
        base_code_version_id=graph.base_code_version_id,
        idempotency_key=scoped_key,
        confirmed_at=_now(),
    )
    db.add(change)
    db.flush()
    return decision, change


def start_simulation(
    db: Session,
    *,
    graph: ProductGraph,
    persona_key: str,
    idempotency_key: str,
) -> tuple[SimulationRun, bool]:
    persona_name = SUPPORTED_PERSONAS.get(persona_key)
    if not persona_name:
        raise ApiError("UNSUPPORTED_SIMULATION_PERSONA", "当前阶段不支持这个虚拟用户。", 422)
    scoped_key = _scoped_key("simulation", graph.id, idempotency_key)
    existing = db.scalar(
        select(SimulationRun).where(SimulationRun.idempotency_key == scoped_key)
    )
    if existing:
        return existing, False
    run = SimulationRun(
        project_id=graph.project_id,
        graph_id=graph.id,
        idempotency_key=scoped_key,
        persona_key=persona_key,
        persona_name=persona_name,
        status=SimulationStatus.QUEUED.value,
        checkpoint_json={"next_position": 0, "completed_node_keys": []},
    )
    db.add(run)
    db.flush()
    return run, True


def finding_response(db: Session, finding: FrictionFinding) -> FrictionFindingResponse:
    node = db.get(JourneyNode, finding.node_id)
    return FrictionFindingResponse(
        id=finding.id,
        run_id=finding.run_id,
        node_id=finding.node_id,
        node_key=node.key if node else "unknown",
        severity=finding.severity,
        status=finding.status,
        product_summary=finding.product_summary,
        evidence=finding.evidence_json,
        resolution_key=finding.resolution_key,
        resolution_options=FINDING_RESOLUTIONS,
        resolved_at=finding.resolved_at,
        created_at=finding.created_at,
    )


def simulation_response(db: Session, run: SimulationRun) -> SimulationRunResponse:
    steps = list(
        db.scalars(
            select(SimulationStep)
            .where(SimulationStep.run_id == run.id)
            .order_by(SimulationStep.sequence)
        )
    )
    findings = list(
        db.scalars(
            select(FrictionFinding)
            .where(FrictionFinding.run_id == run.id)
            .order_by(FrictionFinding.created_at)
        )
    )
    step_responses: list[SimulationStepResponse] = []
    for step in steps:
        node = db.get(JourneyNode, step.node_id)
        step_responses.append(
            SimulationStepResponse(
                id=step.id,
                run_id=step.run_id,
                node_id=step.node_id,
                node_key=node.key if node else "unknown",
                node_title=node.title if node else "未知节点",
                sequence=step.sequence,
                status=step.status,
                observation=step.observation,
                technical_evidence=step.technical_evidence_json,
                duration_ms=step.duration_ms,
                created_at=step.created_at,
            )
        )
    return SimulationRunResponse(
        id=run.id,
        project_id=run.project_id,
        graph_id=run.graph_id,
        persona_key=run.persona_key,
        persona_name=run.persona_name,
        status=run.status,
        current_node_id=run.current_node_id,
        checkpoint=run.checkpoint_json,
        steps=step_responses,
        findings=[finding_response(db, item) for item in findings],
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _observation(node: JourneyNode) -> str:
    messages = {
        "target_user": "虚拟用户能立即判断这个产品是在帮助自己，而不是通用 AI 聊天框。",
        "input": "虚拟用户看懂了输入标准，并能用示例完成第一次提交。",
        "ai_analysis": "处理过程只展示可理解状态，虚拟用户没有看到内部提示词或程序日志。",
        "result": "虚拟用户能分别找到结论、薄弱点和下一步，不需要阅读整段技术输出。",
        "history": "虚拟用户刷新后仍能找到历史结果和对应版本。",
    }
    return messages.get(node.key, f"虚拟用户已完成“{node.title}”。")


def advance_simulation(db: Session, run: SimulationRun) -> SimulationRun:
    if run.status in {
        SimulationStatus.SUCCEEDED.value,
        SimulationStatus.FAILED.value,
        SimulationStatus.CANCELED.value,
    }:
        return run
    if run.status == SimulationStatus.BLOCKED.value:
        unresolved = db.scalar(
            select(FrictionFinding).where(
                FrictionFinding.run_id == run.id,
                FrictionFinding.status == FindingStatus.OPEN.value,
            )
        )
        if unresolved:
            raise ApiError("SIMULATION_BLOCKED", "虚拟用户遇到了阻碍，请先处理发现的问题。", 409)

    nodes = list(
        db.scalars(
            select(JourneyNode)
            .where(JourneyNode.graph_id == run.graph_id)
            .order_by(JourneyNode.position)
        )
    )
    if not nodes:
        raise ApiError("PRODUCT_GRAPH_EMPTY", "产品流程图没有可走查的节点。", 409)

    checkpoint = dict(run.checkpoint_json or {})
    next_position = int(checkpoint.get("next_position", 0))
    completed = list(checkpoint.get("completed_node_keys", []))
    if next_position >= len(nodes):
        run.status = SimulationStatus.SUCCEEDED.value
        run.completed_at = run.completed_at or _now()
        run.current_node_id = None
        return run

    if run.started_at is None:
        run.started_at = _now()
    run.status = SimulationStatus.RUNNING.value
    node = nodes[next_position]
    run.current_node_id = node.id
    sequence = int(
        db.scalar(select(func.max(SimulationStep.sequence)).where(SimulationStep.run_id == run.id))
        or 0
    ) + 1

    if node.key == "input" and node.status != JourneyNodeStatus.OPTIMIZED.value:
        node.status = JourneyNodeStatus.ISSUE.value
        step = SimulationStep(
            run_id=run.id,
            node_id=node.id,
            sequence=sequence,
            status=SimulationStepStatus.BLOCKED.value,
            observation="虚拟用户停在输入框前：不知道应该写多长，也没有可照着填写的例子。",
            technical_evidence_json={
                "check": "input_guidance_present",
                "result": False,
                "contract": node.technical_contract_json,
            },
            duration_ms=180,
        )
        db.add(step)
        existing_finding = db.scalar(
            select(FrictionFinding).where(
                FrictionFinding.run_id == run.id,
                FrictionFinding.node_id == node.id,
                FrictionFinding.status == FindingStatus.OPEN.value,
            )
        )
        if not existing_finding:
            db.add(
                FrictionFinding(
                    run_id=run.id,
                    node_id=node.id,
                    severity=FindingSeverity.BLOCKER.value,
                    status=FindingStatus.OPEN.value,
                    product_summary="新用户不知道输入什么，第一步就可能离开。",
                    evidence_json={
                        "persona": run.persona_name,
                        "observed_at": "input",
                        "missing": ["真实示例", "输入长度预期"],
                        "technical_check": "input_guidance_present=false",
                    },
                )
            )
        run.status = SimulationStatus.BLOCKED.value
        checkpoint["blocked_at"] = node.key
        run.checkpoint_json = checkpoint
        db.flush()
        return run

    db.add(
        SimulationStep(
            run_id=run.id,
            node_id=node.id,
            sequence=sequence,
            status=SimulationStepStatus.PASSED.value,
            observation=_observation(node),
            technical_evidence_json={
                "check": f"{node.key}_contract_available",
                "result": True,
                "contract": node.technical_contract_json,
            },
            duration_ms=120 + node.position * 35,
        )
    )
    if node.key not in completed:
        completed.append(node.key)
    next_position += 1
    checkpoint = {"next_position": next_position, "completed_node_keys": completed}
    run.checkpoint_json = checkpoint
    if next_position >= len(nodes):
        run.status = SimulationStatus.SUCCEEDED.value
        run.completed_at = _now()
        run.current_node_id = None
    db.flush()
    return run


def resolve_finding(
    db: Session,
    *,
    finding: FrictionFinding,
    resolution_key: str,
    idempotency_key: str,
) -> tuple[FrictionFinding, SimulationRun, ProductChangeRequest]:
    allowed = {item["key"]: item for item in FINDING_RESOLUTIONS}
    resolution = allowed.get(resolution_key)
    if not resolution:
        raise ApiError("FINDING_RESOLUTION_NOT_SUPPORTED", "当前阶段不支持这个处理方式。", 422)
    scoped_key = _scoped_key("finding", finding.id, idempotency_key)
    if finding.status == FindingStatus.RESOLVED.value:
        if (
            finding.resolution_idempotency_key != scoped_key
            or finding.resolution_key != resolution_key
        ):
            raise ApiError("FINDING_ALREADY_RESOLVED", "这个问题已经处理，不能重复改选。", 409)
        change = db.scalar(
            select(ProductChangeRequest).where(ProductChangeRequest.idempotency_key == scoped_key)
        )
        run = db.get(SimulationRun, finding.run_id)
        if not change or not run:
            raise ApiError("FINDING_RESOLUTION_INCOMPLETE", "问题处理记录不完整。", 500)
        return finding, run, change

    run = db.get(SimulationRun, finding.run_id)
    node = db.get(JourneyNode, finding.node_id)
    if not run or not node:
        raise not_found("走查记录")
    graph = db.get(ProductGraph, run.graph_id)
    if not graph:
        raise not_found("产品流程图")

    finding.status = FindingStatus.RESOLVED.value
    finding.resolution_key = resolution_key
    finding.resolution_idempotency_key = scoped_key
    finding.resolved_at = _now()
    node.status = JourneyNodeStatus.OPTIMIZED.value
    run.status = SimulationStatus.RUNNING.value
    checkpoint = dict(run.checkpoint_json or {})
    checkpoint.pop("blocked_at", None)
    run.checkpoint_json = checkpoint

    change = ProductChangeRequest(
        project_id=run.project_id,
        graph_id=run.graph_id,
        node_id=node.id,
        source_type=ChangeRequestSource.SIMULATION.value,
        source_id=finding.id,
        status=ChangeRequestStatus.CONFIRMED.value,
        scope_classification=ScopeClassification.IN_SCOPE.value,
        product_request=f"在“{node.title}”节点{resolution['title']}。",
        product_impact_json={
            "user_problem": finding.product_summary,
            "expected_result": resolution["description"],
        },
        technical_context_json=resolution["technical_effects"],
        base_artifact_id=graph.source_artifact_id,
        base_code_version_id=graph.base_code_version_id,
        idempotency_key=scoped_key,
        confirmed_at=_now(),
    )
    db.add(change)
    db.flush()
    return finding, run, change


def latest_simulation(db: Session, graph_id: str) -> SimulationRun | None:
    return db.scalar(
        select(SimulationRun)
        .where(SimulationRun.graph_id == graph_id)
        .order_by(SimulationRun.created_at.desc(), SimulationRun.id.desc())
        .limit(1)
    )


def dashboard_next_action(db: Session, graph: ProductGraph) -> NextAction:
    open_decisions = int(
        db.scalar(
            select(func.count(ProductDecision.id)).where(
                ProductDecision.graph_id == graph.id,
                ProductDecision.status == DecisionStatus.OPEN.value,
            )
        )
        or 0
    )
    run = latest_simulation(db, graph.id)
    if run and run.status == SimulationStatus.BLOCKED.value:
        return NextAction(code="resolve_friction", message="虚拟用户遇到了阻碍，请先处理走查发现。")
    if open_decisions:
        return NextAction(
            code="review_product_decisions",
            message=f"还有 {open_decisions} 个产品决策需要确认，每个选项都附带范围和技术影响。",
        )
    if not run:
        return NextAction(code="start_user_simulation", message="产品流程已确认，可以让虚拟用户走一遍。")
    if run.status in {SimulationStatus.QUEUED.value, SimulationStatus.RUNNING.value}:
        return NextAction(code="continue_user_simulation", message="继续下一步虚拟用户走查。")
    return NextAction(code="review_change_requests", message="走查已完成，请检查已确认的改动请求。")


def dashboard_response(db: Session, graph: ProductGraph) -> ProductDashboardResponse:
    run = latest_simulation(db, graph.id)
    open_findings = list(
        db.scalars(
            select(FrictionFinding)
            .join(SimulationRun, SimulationRun.id == FrictionFinding.run_id)
            .where(
                SimulationRun.graph_id == graph.id,
                FrictionFinding.status == FindingStatus.OPEN.value,
            )
            .order_by(FrictionFinding.created_at)
        )
    )
    changes = list(
        db.scalars(
            select(ProductChangeRequest)
            .where(
                ProductChangeRequest.graph_id == graph.id,
                ProductChangeRequest.status.in_(
                    [ChangeRequestStatus.CONFIRMED.value, ChangeRequestStatus.QUEUED.value]
                ),
            )
            .order_by(ProductChangeRequest.created_at)
        )
    )
    return ProductDashboardResponse(
        project_id=graph.project_id,
        graph=graph_response(db, graph),
        decision_center=decision_center_response(db, graph),
        latest_simulation=simulation_response(db, run) if run else None,
        open_findings=[finding_response(db, item) for item in open_findings],
        queued_changes=[change_request_response(item) for item in changes],
        next_action=dashboard_next_action(db, graph),
    )


def owned_decision(db: Session, decision_id: str, user_id: str) -> ProductDecision:
    decision = db.scalar(
        select(ProductDecision)
        .join(Project, Project.id == ProductDecision.project_id)
        .where(ProductDecision.id == decision_id, Project.owner_id == user_id)
    )
    if not decision:
        raise not_found("产品决策")
    return decision


def owned_simulation(db: Session, run_id: str, user_id: str) -> SimulationRun:
    run = db.scalar(
        select(SimulationRun)
        .join(Project, Project.id == SimulationRun.project_id)
        .where(SimulationRun.id == run_id, Project.owner_id == user_id)
    )
    if not run:
        raise not_found("虚拟用户走查")
    return run


def owned_finding(db: Session, finding_id: str, user_id: str) -> FrictionFinding:
    finding = db.scalar(
        select(FrictionFinding)
        .join(SimulationRun, SimulationRun.id == FrictionFinding.run_id)
        .join(Project, Project.id == SimulationRun.project_id)
        .where(FrictionFinding.id == finding_id, Project.owner_id == user_id)
    )
    if not finding:
        raise not_found("走查发现")
    return finding
