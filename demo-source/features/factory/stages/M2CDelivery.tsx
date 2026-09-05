"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Check, Download, FileArchive, FileCheck2, Github, PackageCheck, Send, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api/client";
import type { DeliveryPackage, Deployment, GithubSync, PlatformCapabilities } from "@/lib/api/types";
import type { StageProps } from "../StagePanels";
import { EmptyState, humanize, Panel, StageIntro, StatusPill, stringify } from "../StageUi";
import { formatBytes, formatDate } from "../data";

export function M2CDelivery({ project, onError, onNotice, onNavigate }: StageProps) {
  const [packages, setPackages] = useState<DeliveryPackage[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [capabilities, setCapabilities] = useState<PlatformCapabilities | null>(null);
  const [repository, setRepository] = useState("");
  const [sync, setSync] = useState<GithubSync | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [packageResult, deploymentResult, runtime] = await Promise.all([api.deliveryPackages(project.id), api.deployments(project.id), api.capabilities()]);
      setPackages(packageResult.items);
      setDeployments(deploymentResult.items);
      setCapabilities(runtime);
    } catch (value) { onError(value); }
  }, [onError, project.id]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function createPackage(deploymentId: string) {
    setBusy(true);
    try {
      await api.createDeliveryPackage(project.id, deploymentId);
      await load();
      onNotice("完整交付包已经生成，敏感授权信息不会包含在其中。");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  async function syncGithub(packageId: string) {
    if (!repository.trim()) return;
    setBusy(true);
    try {
      const result = await api.syncGithub(packageId, repository.trim());
      setSync(result);
      onNotice(result.status === "succeeded" ? "源码已同步到 GitHub。" : "GitHub 同步请求已记录。 ");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  const latestPackage = packages[0];
  const latestDeployment = deployments[0];
  const successfulDeployment = deployments.find((item) => item.status === "succeeded" && Boolean(item.deployment_url));
  const realGithubSyncAvailable = capabilities?.github_sync_mode === "external";
  const realDeploymentAvailable = Boolean(capabilities?.deployment_enabled && capabilities.deployment_mode === "external");
  const deliveryItems = [
    "最终产品需求与确认方案",
    "线上地址与产品使用说明",
    "完整源代码与必要配置",
    "质量检查结果摘要",
    "启动、更新与恢复说明",
    "不含任何敏感授权信息的配置模板",
  ];

  return (
    <>
      <StageIntro eyebrow="第 4 步 · 交付内容" title="网址上线不是终点，整个产品都交给你" description="交付内容与线上版本保持一致，包括产品方案、使用说明、质量结果和完整源代码。你可以下载保存，也可以交给其他团队继续维护。" aside={<div className="safety-badge"><PackageCheck size={20} /><div><strong>可下载、可带走</strong><small>版本一致 · 敏感信息已排除</small></div></div>} />

      {capabilities && (!realDeploymentAvailable || latestDeployment?.status === "simulated") && <section className="reality-status-card warning" aria-label="真实交付状态"><span><ShieldCheck size={19} /></span><div><small>真实交付状态</small><strong>{latestDeployment?.status === "simulated" ? "当前只有发布演练记录，尚无线上版本" : "尚无真实上线版本，正式交付未开始"}</strong><p>{latestDeployment?.status === "simulated" ? "演练没有创建云资源和线上地址，因此不能生成声称与线上版本一致的正式交付包。" : "真实发布服务尚未启用。交付包只会在获得真实线上地址后生成，不会使用测试数据假装已经交付。"}</p></div><button className="ghost-button" type="button" onClick={() => onNavigate("m2b")}>查看发布状态<ArrowRight size={15} /></button></section>}

      <div className="delivery-grid">
        <Panel title={latestPackage ? "本次交付包包含" : "正式交付包将包含"}>
          <div className="delivery-checklist">{deliveryItems.map((item) => <div key={item}><span><Check size={14} /></span><strong>{item}</strong></div>)}</div>
          <div className="secret-scan"><ShieldCheck size={18} /><div><strong>敏感授权信息不会进入交付包</strong><p>你可以安全地下载、保存或交给其他团队。</p></div></div>
          {!successfulDeployment ? <EmptyState title="产品上线后才能生成交付包" description="交付包需要与一个已经上线的版本绑定，确保线上产品、文档和下载内容保持一致。" action={<button className="ghost-button" type="button" onClick={() => onNavigate("m2b")}>返回发布产品<ArrowRight size={15} /></button>} /> : !latestPackage ? <button className="primary-button wide" type="button" onClick={() => void createPackage(successfulDeployment.id)} disabled={busy}><FileArchive size={17} />{busy ? "正在整理交付内容…" : "生成完整交付包"}</button> : null}
        </Panel>

        <Panel title="最新交付版本">
          {!latestPackage ? <EmptyState title="交付包尚未生成" description="产品上线后，点击左侧按钮即可生成与线上版本一致的完整交付内容。" /> : <div className="package-card"><div className="package-head"><span><FileArchive size={22} /></span><div><small>交付版本 {latestPackage.revision}</small><h2>{latestPackage.filename}</h2></div><StatusPill status={latestPackage.status} /></div><div className="package-facts"><div><span>文件大小</span><strong>{formatBytes(latestPackage.size_bytes)}</strong></div><div><span>生成时间</span><strong>{formatDate(latestPackage.created_at)}</strong></div></div><a className="primary-button wide" href={api.downloadUrl(latestPackage.id)}><Download size={17} />下载完整产品交付包</a></div>}
        </Panel>
      </div>

      {latestPackage && (
        <details className="implementation-details delivery-implementation-details">
          <summary><span>实现与接手说明</span><small>技术团队接手时查看</small></summary>
          <div className="delivery-lower-grid">
          <Panel title="交付包内容证明">
            <div className="manifest-grid">{Object.entries(latestPackage.manifest).slice(0, 12).map(([key, value]) => <div key={key}><FileCheck2 size={15} /><span>{humanize(key)}</span><strong>{stringify(value)}</strong></div>)}</div>
          </Panel>
          <Panel title="同步到你的 GitHub" action={<Github size={18} />}>
            {realGithubSyncAvailable ? <><p className="section-description">这是可选操作。平台不会在未确认时创建仓库或覆盖分支。</p>
            <form className="github-form" onSubmit={(event) => { event.preventDefault(); void syncGithub(latestPackage.id); }}><label>仓库名称<input value={repository} onChange={(event) => setRepository(event.target.value)} placeholder="你的账号/仓库名称" pattern="[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+" /></label><button className="ghost-button wide" type="submit" disabled={busy || !repository.trim()}><Send size={15} />确认同步到 main 分支</button></form>
            {sync && <div className="sync-result"><StatusPill status={sync.status} /><div><strong>{sync.repository_full_name}</strong><small>{sync.repository_url ?? sync.error_code ?? "同步记录已创建"}</small></div></div>}</> : <EmptyState title="真实 GitHub 同步尚未启用" description="当前不会模拟创建仓库。你仍可以下载完整交付包，再由自己或技术团队上传到代码仓库。" />}
          </Panel>
          </div>
        </details>
      )}
    </>
  );
}
