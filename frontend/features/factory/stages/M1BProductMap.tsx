"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Check, ChevronRight, CircleAlert, Eye, MapPinned, Play, RotateCw, UserRound } from "lucide-react";
import { api, isAppError } from "@/lib/api/client";
import type { ProductDashboard, Simulation } from "@/lib/api/types";
import type { StageProps } from "../StagePanels";
import { EmptyState, Panel, StageIntro, StatusPill } from "../StageUi";

export function M1BProductMap({ project, onError, onNotice, onNavigate }: StageProps) {
  const [dashboard, setDashboard] = useState<ProductDashboard | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await api.productDashboard(project.id);
      setDashboard(response);
      setSelectedNode((current) => current ?? response.graph.nodes[0]?.id ?? null);
    } catch (value) {
      if (isAppError(value) && value.status === 404) setDashboard(null);
      else onError(value);
    }
  }, [onError, project.id]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function initialize() {
    setBusy(true);
    try {
      await api.initializeGraph(project.id);
      await load();
      onNotice("产品流程已生成，需要你确认的关键选择已经标出来了。");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  async function confirmDecision(decisionId: string, optionKey: string) {
    setBusy(true);
    try {
      await api.confirmDecision(decisionId, optionKey);
      await load();
      onNotice("这个产品决策已经确认，并记录了对应改动。");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  async function startSimulation() {
    if (!dashboard) return;
    setBusy(true);
    try {
      await api.startSimulation(dashboard.graph.id);
      await load();
      onNotice("虚拟用户已经进入产品，可以逐步查看它在哪里顺利、在哪里卡住。");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  async function advanceSimulation(run: Simulation) {
    setBusy(true);
    try {
      await api.advanceSimulation(run.id);
      await load();
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  async function resolveFinding(id: string) {
    setBusy(true);
    try {
      await api.resolveFinding(id, "explain_before_input");
      await load();
      onNotice("问题已转成明确的产品改动，并加入后续开发队列。");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  if (!dashboard) {
    return (
      <>
        <StageIntro eyebrow="第 2 步 · 产品流程" title="先看懂产品怎么用，再开始生成" description="把已确认的方案转换成一条可点击的使用流程，提前确认关键选择，并让一位虚拟用户完整走一遍。" />
        <Panel><EmptyState title="为这个项目生成产品流程" description="产品流程不会改变已确认的方案，它会把用户看到的内容、每一步目的和需要确认的选择放在一起。" action={<button className="primary-button" type="button" onClick={() => void initialize()} disabled={busy}>{busy ? "正在生成…" : "生成产品流程"}<ArrowRight size={16} /></button>} /></Panel>
      </>
    );
  }

  const activeNode = dashboard.graph.nodes.find((item) => item.id === selectedNode) ?? dashboard.graph.nodes[0];
  const simulation = dashboard.latest_simulation;
  const allDecisionsConfirmed = dashboard.decision_center.open_count === 0;
  return (
    <>
      <StageIntro eyebrow="第 2 步 · 产品流程" title="不用读代码，也能看见产品怎么工作" description="每一步都会说明用户看见什么、为什么需要这一步，以及工厂会在背后完成什么。" aside={<div className="stage-score"><span>{dashboard.graph.nodes.length}</span><div><strong>个使用步骤</strong><small>产品流程第 {dashboard.graph.version} 版</small></div></div>} />

      <Panel className="product-map-card" title={dashboard.graph.title} action={<StatusPill status={dashboard.graph.status} />}>
        <p className="map-goal">{dashboard.graph.product_goal}</p>
        <div className="journey-map" role="list" aria-label="产品用户旅程">
          {dashboard.graph.nodes.map((node, index) => (
            <div className="journey-step-wrap" key={node.id} role="listitem">
              <button type="button" className={`journey-step ${activeNode?.id === node.id ? "active" : ""}`} onClick={() => setSelectedNode(node.id)}>
                <span>{node.node_type === "persona" ? <UserRound size={18} /> : node.node_type === "output" ? <Eye size={18} /> : <MapPinned size={18} />}</span>
                <small>步骤 {index + 1}</small><strong>{node.title}</strong><p>{node.caption}</p><StatusPill status={node.status} />
              </button>
              {index < dashboard.graph.nodes.length - 1 && <ChevronRight className="journey-arrow" size={21} />}
            </div>
          ))}
        </div>
        {activeNode && (
          <div className="node-inspector">
            <div><span>这个步骤的产品目的</span><strong>{activeNode.product_purpose}</strong></div>
            <div><span>用户会看见</span><strong>{activeNode.user_sees}</strong></div>
            <div><span>系统在背后做</span><strong>{activeNode.system_does}</strong></div>
            <details className="implementation-details"><summary><span>实现说明</span><small>给技术接手或排查问题时查看</small></summary><pre>{JSON.stringify(activeNode.technical_contract, null, 2)}</pre></details>
          </div>
        )}
      </Panel>

      <div className="map-lower-grid">
        <Panel title={`关键决策 · ${dashboard.decision_center.confirmed_count}/${dashboard.decision_center.items.length} 已确认`}>
          <div className="decision-stack">
            {dashboard.decision_center.items.length === 0 && <p className="muted-copy">当前没有需要用户确认的关键决策。</p>}
            {dashboard.decision_center.items.map((decision) => (
              <article className="decision-card" key={decision.id}>
                <div><StatusPill status={decision.status} /><small>{decision.title}</small></div>
                <h3>{decision.question}</h3>
                <div className="decision-options">
                  {decision.options.map((option) => (
                    <button type="button" key={option.id} disabled={busy || decision.status === "confirmed"} className={decision.selected_option_key === option.key ? "selected" : ""} onClick={() => void confirmDecision(decision.id, option.key)}>
                      <span>{option.recommended ? "推荐" : "可选"}</span><strong>{option.title}</strong><p>{option.description}</p>{decision.selected_option_key === option.key && <Check size={16} />}
                    </button>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </Panel>

        <Panel title="虚拟用户走查" action={simulation && <StatusPill status={simulation.status} />}>
          {!simulation ? (
            <EmptyState title={allDecisionsConfirmed ? "让第一位虚拟用户体验" : "先确认关键产品决策"} description={allDecisionsConfirmed ? "系统会模拟一个第一次使用产品的非技术用户，逐步检查理解和操作障碍。" : `还有 ${dashboard.decision_center.open_count} 个决策未确认。`} action={allDecisionsConfirmed ? <button className="primary-button" type="button" onClick={() => void startSimulation()} disabled={busy}><Play size={16} />开始走查</button> : undefined} />
          ) : (
            <div className="simulation-panel">
              <div className="persona-row"><span><UserRound size={19} /></span><div><strong>{simulation.persona_name}</strong><small>第一次使用 · 不懂技术 · 目标导向</small></div></div>
              <div className="simulation-timeline">
                {simulation.steps.map((step) => <div key={step.id} className={step.status}><span>{step.status === "passed" ? <Check size={14} /> : <CircleAlert size={14} />}</span><div><strong>{step.node_title}</strong><p>{step.observation}</p></div><small>{step.duration_ms} ms</small></div>)}
              </div>
              {simulation.findings.filter((item) => item.status === "open").map((finding) => <div className="finding-card" key={finding.id}><CircleAlert size={18} /><div><strong>{finding.product_summary}</strong><p>系统已准备两种改法，采用后会加入开发队列。</p></div><button className="ghost-button" type="button" disabled={busy} onClick={() => void resolveFinding(finding.id)}>采用推荐改法</button></div>)}
              {["queued", "running", "blocked"].includes(simulation.status) && <button className="primary-button wide" type="button" onClick={() => void advanceSimulation(simulation)} disabled={busy}><RotateCw size={16} />继续下一步走查</button>}
              {simulation.status === "succeeded" && dashboard.open_findings.length === 0 && <button className="primary-button wide" type="button" onClick={() => onNavigate("m1c")}>流程确认，开始生成产品<ArrowRight size={16} /></button>}
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
