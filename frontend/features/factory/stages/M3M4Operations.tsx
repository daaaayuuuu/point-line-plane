"use client";

import { useState } from "react";
import { Activity, ArrowRight, Check, Copy, Database, HardDriveDownload, KeyRound, LockKeyhole, RefreshCw, ShieldCheck, UserPlus, UsersRound } from "lucide-react";
import { api } from "@/lib/api/client";
import type { Backup, BetaInvite, OperationsMetrics } from "@/lib/api/types";
import type { StageProps } from "../StagePanels";
import { EmptyState, humanize, Panel, StageIntro, StatusPill } from "../StageUi";
import { formatBytes, formatDate } from "../data";

export function M3M4Operations({ onError, onNotice }: StageProps) {
  const [token, setToken] = useState("");
  const [metrics, setMetrics] = useState<OperationsMetrics | null>(null);
  const [invites, setInvites] = useState<BetaInvite[]>([]);
  const [backups, setBackups] = useState<Backup[]>([]);
  const [inviteLabel, setInviteLabel] = useState("首轮内测用户");
  const [inviteCode, setInviteCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);

  async function loadOperations() {
    if (!token.trim()) return;
    setBusy(true);
    try {
      const [metricResult, inviteResult, backupResult] = await Promise.all([
        api.operationsMetrics(token.trim()),
        api.betaInvites(token.trim()),
        api.backups(token.trim()),
      ]);
      setMetrics(metricResult);
      setInvites(inviteResult);
      setBackups(backupResult);
      setConnected(true);
      onNotice("运营视图已连接，敏感令牌只保存在当前输入框内。 ");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  async function createInvite() {
    if (inviteCode.length < 12) return;
    setBusy(true);
    try {
      await api.createBetaInvite(token.trim(), inviteCode.trim(), inviteLabel.trim());
      setInviteCode("");
      setInvites(await api.betaInvites(token.trim()));
      onNotice("新的内测邀请码已创建，明文不会再次显示。请妥善保存刚才输入的内容。");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  async function createBackup() {
    if (!window.confirm("确认立即创建一次业务数据备份吗？")) return;
    setBusy(true);
    try {
      await api.createBackup(token.trim());
      setBackups(await api.backups(token.trim()));
      onNotice("备份任务已完成并记录完整性校验。 ");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  async function copyText(value: string) {
    await navigator.clipboard.writeText(value);
    onNotice("已复制。 ");
  }

  return (
    <>
      <StageIntro eyebrow="M3 / M4 · 真实案例与邀请内测" title="从一个人能用，走向多人稳定使用" description="运营视图用于查看数据库状态、失败趋势、备份和邀请码。它与普通产品工作区隔离，需要单独的运维令牌。" aside={<div className="safety-badge"><ShieldCheck size={20} /><div><strong>运维权限隔离</strong><small>限流 · 备份 · 审计</small></div></div>} />

      {!connected ? (
        <Panel className="operations-login"><span className="operations-lock"><LockKeyhole size={24} /></span><div><span className="eyebrow">受保护的运营视图</span><h2>连接后查看运行状态</h2><p>运维令牌不会写入 URL、浏览器存储或项目交付物。</p></div><form onSubmit={(event) => { event.preventDefault(); void loadOperations(); }}><label>运维令牌<input type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="请输入运维令牌" autoComplete="off" /></label><button className="primary-button" type="submit" disabled={busy || !token.trim()}>{busy ? "正在验证…" : "进入运营视图"}<ArrowRight size={16} /></button></form></Panel>
      ) : (
        <>
          <div className="operations-metrics">
            <Panel className="ops-metric"><span><Database size={18} /></span><small>数据库状态</small><strong>{String(metrics?.database.status ?? metrics?.database.engine ?? "可用")}</strong><p>就绪检查与业务数据分离</p></Panel>
            {Object.entries(metrics?.counts ?? {}).slice(0, 3).map(([key, value]) => <Panel className="ops-metric" key={key}><span><Activity size={18} /></span><small>{humanize(key)}</small><strong>{value.toLocaleString("zh-CN")}</strong><p>当前累计真实记录</p></Panel>)}
          </div>

          <div className="operations-grid">
            <Panel title="内测邀请码" action={<button className="icon-button" type="button" onClick={() => void loadOperations()} aria-label="刷新运营数据"><RefreshCw size={16} /></button>}>
              <form className="invite-form" onSubmit={(event) => { event.preventDefault(); void createInvite(); }}><label>用户标签<input value={inviteLabel} onChange={(event) => setInviteLabel(event.target.value)} /></label><label>新邀请码<input type="password" value={inviteCode} onChange={(event) => setInviteCode(event.target.value)} minLength={12} placeholder="至少 12 位，仅创建时显示" autoComplete="new-password" /></label><button className="ghost-button wide" type="submit" disabled={busy || inviteCode.length < 12}><UserPlus size={15} />创建单用户邀请码</button></form>
              <div className="invite-list">{invites.length === 0 ? <EmptyState title="还没有运营邀请码" description="创建后可以邀请第一批真实用户，并限制使用次数与有效期。" /> : invites.map((item) => <article key={item.id}><span><UsersRound size={16} /></span><div><strong>{item.label}</strong><small>{formatDate(item.created_at)} · 使用 {item.use_count}/{item.max_uses}</small></div><StatusPill status={item.status} /></article>)}</div>
            </Panel>

            <Panel title="数据备份">
              <div className="backup-summary"><span><HardDriveDownload size={21} /></span><div><strong>{backups.length ? `${backups.length} 个可追溯备份` : "尚未创建备份"}</strong><p>备份包含完整性校验，可用于数据恢复与审计追踪。</p></div></div>
              <button className="primary-button wide" type="button" onClick={() => void createBackup()} disabled={busy}><HardDriveDownload size={16} />立即创建安全备份</button>
              <div className="backup-list">{backups.slice(0, 5).map((item) => <article key={item.id}><span className={item.status}><Check size={14} /></span><div><strong>{item.mode === "sqlite_local" ? "业务数据备份" : "托管数据备份"}</strong><small>{formatDate(item.created_at)} · {formatBytes(item.size_bytes)}</small></div><StatusPill status={item.status} />{item.sha256 && <button className="icon-button" type="button" onClick={() => void copyText(item.sha256 ?? "")} aria-label="复制校验值"><Copy size={14} /></button>}</article>)}</div>
            </Panel>
          </div>

          <Panel title="最近失败趋势" action={<span className="technical-label"><Activity size={14} />只显示脱敏聚合数据</span>}>
            {Object.keys(metrics?.recent_failures ?? {}).length === 0 ? <div className="healthy-state"><Check size={18} /><div><strong>近期没有记录到系统性失败</strong><p>任务、部署和外部适配器异常会按类型聚合，不上传用户完整输入。</p></div></div> : <div className="failure-grid">{Object.entries(metrics?.recent_failures ?? {}).map(([key, value]) => <div key={key}><span>{humanize(key)}</span><strong>{value}</strong></div>)}</div>}
            <div className="operations-footer"><span><KeyRound size={15} />运营数据生成于 {formatDate(metrics?.generated_at)}</span><button className="ghost-button" type="button" onClick={() => { setConnected(false); setMetrics(null); }}>退出运营视图</button></div>
          </Panel>
        </>
      )}
    </>
  );
}
