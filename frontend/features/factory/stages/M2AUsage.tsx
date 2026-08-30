"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, Check, Eye, EyeOff, KeyRound, LockKeyhole, PlugZap, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import { api } from "@/lib/api/client";
import type { ModelCredential, PlatformCapabilities, UsageLedger, UsageSummary } from "@/lib/api/types";
import type { StageProps } from "../StagePanels";
import { EmptyState, KeyValue, Panel, StageIntro, StatusPill } from "../StageUi";
import { formatDate } from "../data";

const OPERATION_LABELS: Record<string, string> = {
  requirements_prd: "整理产品需求",
  solution: "生成产品方案",
  development: "生成产品",
  repair: "自动修复",
  preview_run: "运行产品预览",
  credential_verify: "验证 AI 服务",
};

export function M2AUsage({ project, onError, onNotice, onNavigate }: StageProps) {
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [ledger, setLedger] = useState<UsageLedger[]>([]);
  const [credentials, setCredentials] = useState<ModelCredential[]>([]);
  const [capabilities, setCapabilities] = useState<PlatformCapabilities | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [scope, setScope] = useState("both");
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [usage, history, keys, runtime] = await Promise.all([
        api.usageSummary(),
        api.usageLedger(project.id),
        api.modelCredentials(),
        api.capabilities(),
      ]);
      setSummary(usage);
      setLedger(history.items);
      setCredentials(keys.items);
      setCapabilities(runtime);
    } catch (value) { onError(value); }
  }, [onError, project.id]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function connect() {
    if (!apiKey.trim()) return;
    setBusy(true);
    try {
      const created = await api.connectModelCredential(apiKey.trim(), project.id, scope);
      setCredentials((items) => [created, ...items]);
      setApiKey("");
      onNotice("AI 服务授权已安全保存，页面中只会显示脱敏提示。");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  async function verify(id: string) {
    setBusy(true);
    try {
      await api.verifyModelCredential(id);
      await load();
      onNotice("AI 服务连接验证通过，本次少量使用已经记录。");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  async function revoke(id: string) {
    if (!window.confirm("撤销后工厂将无法再使用这项 AI 服务授权，确定继续吗？")) return;
    setBusy(true);
    try {
      await api.revokeModelCredential(id);
      await load();
      onNotice("AI 服务授权已撤销，保存的信息已经删除。");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  const quotaPercent = useMemo(() => {
    if (!summary?.quota.granted_units) return 0;
    return Math.min(100, Math.round((summary.quota.consumed_units / summary.quota.granted_units) * 100));
  }, [summary]);
  const realUsage = ledger.filter((item) => item.source !== "mock" && item.provider !== "mock");
  const simulatedUsage = ledger.filter((item) => item.source === "mock" || item.provider === "mock");
  const verifiedCredentials = credentials.filter((item) => item.status === "verified" && (!item.project_id || item.project_id === project.id));
  const actualCostMicrousd = realUsage.reduce((total, item) => total + (item.estimated_cost_microusd ?? 0), 0);
  const planLabel = summary?.quota.plan === "internal_free" ? "产品自带额度" : summary?.quota.plan ?? "额度状态读取中";
  const generationMode = realUsage.length > 0 || capabilities?.ai_provider_mode === "verified" ? "真实服务" : "体验模式";

  return (
    <>
      <StageIntro eyebrow="第 3 步 · AI 服务与费用" title="AI 在哪里工作、可能花多少，一眼看明白" description="工厂会优先使用产品自带额度。只有额度不足或你希望使用自己的 AI 服务时，才需要额外授权；任何可能产生的费用都会先说明。" aside={<div className="safety-badge"><LockKeyhole size={20} /><div><strong>授权信息安全保存</strong><small>不会进入聊天、产品或交付物</small></div></div>} />

      {simulatedUsage.length > 0 && realUsage.length === 0 && <section className="reality-status-card warning" aria-label="真实 AI 服务状态"><span><ShieldCheck size={19} /></span><div><small>真实 AI 服务状态</small><strong>当前记录全部来自体验模式</strong><p>后台实际保存了 {simulatedUsage.length} 条流程记录，但没有发生真实模型调用，也没有产生真实模型费用。连接并验证真实服务后，新的调用才会计入正式记录。</p></div></section>}

      <div className="usage-overview">
        <Panel className="quota-card">
          <div className="quota-visual" style={{ "--quota": `${quotaPercent * 3.6}deg` } as React.CSSProperties}><span><strong>{summary?.quota.remaining_units.toLocaleString("zh-CN") ?? "—"}</strong><small>剩余点数</small></span></div>
          <div><span className="eyebrow">{planLabel}</span><h2>可用额度</h2><p>已使用 {summary?.quota.consumed_units.toLocaleString("zh-CN") ?? 0} / {summary?.quota.granted_units.toLocaleString("zh-CN") ?? 0} 点</p><div className="mini-progress"><span style={{ width: `${quotaPercent}%` }} /></div></div>
        </Panel>
        <Panel className="metric-card"><span>真实 AI 调用</span><strong>{realUsage.length}<small> 次</small></strong><p>{verifiedCredentials.length > 0 ? `已有 ${verifiedCredentials.length} 项真实服务授权通过验证` : "尚未连接经过验证的真实 AI 服务"}</p></Panel>
        <Panel className="metric-card"><span>当前生成方式</span><strong>{generationMode}</strong><p>{generationMode === "真实服务" ? "调用来源和结果已记录，可继续核对费用。" : `${simulatedUsage.length} 条体验记录不会冒充真实调用。`}</p></Panel>
        <Panel className="metric-card"><span>实际记录费用</span><strong>${(actualCostMicrousd / 1_000_000).toFixed(4)}</strong><p>{realUsage.some((item) => item.pricing_configured) ? "根据后台真实价格记录汇总" : "尚无已配置价格的真实调用记录"}</p></Panel>
      </div>

      <div className="usage-main-grid">
        <Panel title="连接你自己的 AI 服务（可选）" action={<span className="technical-label"><ShieldCheck size={14} />安全授权</span>}>
          <p className="section-description">如果产品自带额度足够，可以跳过这里。需要连接时，工厂只会在你选择的范围内使用。</p>
          <form className="credential-form" onSubmit={(event) => { event.preventDefault(); void connect(); }}>
            <label>允许使用的范围<select value={scope} onChange={(event) => setScope(event.target.value)}><option value="both">生成产品与上线运行</option><option value="development">只在生成产品时</option><option value="runtime">只在用户使用产品时</option></select></label>
            <label>AI 服务密钥<div className="secret-field"><input type={showKey ? "text" : "password"} value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="粘贴服务商提供的密钥" minLength={8} autoComplete="off" /><button type="button" onClick={() => setShowKey((value) => !value)} aria-label={showKey ? "隐藏密钥" : "显示密钥"}>{showKey ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></label>
            <div className="secret-note"><LockKeyhole size={15} /><span>提交后前端立即清空原文，只保留类似 <b>••••a8T2</b> 的脱敏提示。</span></div>
            <button className="primary-button wide" type="submit" disabled={busy || apiKey.trim().length < 8}><PlugZap size={16} />加密连接</button>
          </form>

          <div className="credential-list">
            {credentials.length === 0 && <EmptyState title="目前不需要额外授权" description="产品自带额度足够时可以直接继续；额度不足时工厂会暂停并解释原因，不会静默扣费。" />}
            {credentials.map((item) => <article key={item.id}><span className="key-icon"><KeyRound size={17} /></span><div><strong>{item.masked_hint}</strong><small>{item.scope === "both" ? "生成与运行" : item.scope === "development" ? "仅生成产品" : "仅产品运行"}</small></div><StatusPill status={item.status} />{item.status === "unverified" && <button className="ghost-button small" type="button" disabled={busy} onClick={() => void verify(item.id)}><RefreshCw size={13} />验证连接</button>}<button className="icon-button danger" type="button" disabled={busy || item.status === "revoked"} onClick={() => void revoke(item.id)} aria-label="撤销 AI 服务授权"><Trash2 size={15} /></button></article>)}
          </div>
        </Panel>

        <Panel title="费用说明">
          <ul className="plain-check-list cost-explanation-list">
            <li><Check size={15} /><span><strong>先用产品自带额度</strong><small>额度足够时，不需要提供额外授权</small></span></li>
            <li><Check size={15} /><span><strong>费用变化会提前说明</strong><small>只有你确认后，才会使用可能产生费用的外部服务</small></span></li>
            <li><Check size={15} /><span><strong>额度不足会暂停</strong><small>不会在后台静默扣费，也不会阻止你取回已有成果</small></span></li>
          </ul>
          <details className="implementation-details usage-ledger-details">
            <summary><span>查看详细使用记录</span><small>{ledger.length} 条可核对记录</small></summary>
            {ledger.length === 0 ? <EmptyState title="暂无使用记录" description="需求、生成、修复和预览的每次 AI 使用都会记录在这里。" /> : <div className="ledger-list">{ledger.map((item) => <article key={item.id}><span className={item.status}><Check size={14} /></span><div><strong>{OPERATION_LABELS[item.operation] ?? item.operation}</strong><small>{formatDate(item.created_at)} · {item.source === "platform_free" ? "产品自带额度" : item.source === "user_key" ? "你的 AI 服务" : "平台 AI 服务"}</small></div><div><b>{item.total_tokens.toLocaleString("zh-CN")}</b><small>技术计量单位</small></div></article>)}</div>}
            <div className="ledger-footer"><KeyValue label="项目使用记录" value={`${ledger.length} 条`} /><KeyValue label="费用追踪" value="已开启" /></div>
          </details>
          <button className="primary-button wide" type="button" onClick={() => onNavigate("m2b")}>继续检查上线条件<ArrowRight size={16} /></button>
        </Panel>
      </div>
    </>
  );
}
