"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, Check, CircleAlert, Code2, FileCode2, Play, RotateCw, ShieldCheck, Wrench } from "lucide-react";
import { api, isAppError } from "@/lib/api/client";
import type { DevelopmentRun, DevelopmentWorkspace, ModelCredential, PlatformCapabilities, Task } from "@/lib/api/types";
import type { StageProps } from "../StagePanels";
import { EmptyState, KeyValue, Panel, StageIntro, StatusPill } from "../StageUi";
import { UI_STYLE_OPTIONS, UiStylePicker, loadUiStylePreference, saveUiStylePreference, type UiStyleKey } from "../UiStylePicker";
import { formatBytes } from "../data";

const STEP_LABELS: Record<string, string> = {
  plan: "确认本次生成范围",
  workspace: "准备产品空间",
  generate: "生成页面与功能",
  validate: "检查功能完整性",
  commit: "保存可恢复版本",
  quality: "检查核心流程",
  preview: "准备测试环境",
};

const TOOL_LABELS: Record<string, string> = {
  write_file: "写入产品文件",
  validate_bundle: "检查代码包",
  git_commit: "保存代码版本",
  compile: "检查代码能否运行",
  pytest: "运行功能测试",
  runtime_smoke: "验证核心流程",
};

function friendlyDevelopmentStep(value: string): string {
  if (value.includes("读取已经确认的 PRD")) return "读取已经确认的产品需求、方案和产品决定";
  if (/文本 Agent 后端代码包|generate.*code/i.test(value)) return "把确认内容变成可以运行的页面和功能";
  if (value.includes("检查文件范围")) return "安全保存产品文件，并检查不会带入密钥等敏感信息";
  if (value.includes("代码版本")) return "保存一个可以追溯和恢复的产品版本";
  if (/编译|自动化测试|接口冒烟/.test(value)) return "检查产品能否打开、核心功能和主要流程";
  if (value.includes("修复版本")) return "发现问题时自动修复，并重新检查";
  if (/真实临时预览|runtime_preview/.test(value)) return "准备与已通过检查的保存版本一致的测试环境";
  return value;
}

export function M1CDevelopment({ project, onProjectChange, onRefresh, onError, onNotice, onNavigate }: StageProps) {
  const [task, setTask] = useState<Task | null>(project.active_task ?? null);
  const [workspace, setWorkspace] = useState<DevelopmentWorkspace | null>(null);
  const [runs, setRuns] = useState<DevelopmentRun[]>([]);
  const [capabilities, setCapabilities] = useState<PlatformCapabilities | null>(null);
  const [credentials, setCredentials] = useState<ModelCredential[]>([]);
  const [uiStyleKey, setUiStyleKey] = useState<UiStyleKey>(() => loadUiStylePreference(project.id) ?? "duolingo-sticker");
  const [hasSavedUiStyle, setHasSavedUiStyle] = useState(() => Boolean(loadUiStylePreference(project.id)));
  const [changingUiStyle, setChangingUiStyle] = useState(() => !loadUiStylePreference(project.id));
  const [busy, setBusy] = useState(false);

  const loadDevelopment = useCallback(async () => {
    try {
      const [runtime, keys] = await Promise.all([api.capabilities(), api.modelCredentials()]);
      setCapabilities(runtime);
      setCredentials(keys.items);
    } catch (value) { onError(value); }
    try {
      const response = await api.developmentRuns(project.id);
      setRuns(response.items);
    } catch (value) {
      if (!(isAppError(value) && (value.status === 404 || value.status === 409))) onError(value);
    }
    try {
      setWorkspace(await api.workspace(project.id));
    } catch (value) {
      if (!(isAppError(value) && (value.status === 404 || value.status === 409))) onError(value);
    }
  }, [onError, project.id]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadDevelopment(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadDevelopment]);

  const currentTask = task ?? project.active_task ?? null;

  useEffect(() => {
    if (!currentTask || !["queued", "running"].includes(currentTask.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const updated = await api.task(currentTask.id);
        setTask(updated);
        if (!["queued", "running"].includes(updated.status)) {
          await loadDevelopment();
          await onRefresh();
          if (updated.status === "succeeded") onNotice("前后端应用和质量检查已经准备好，可以进入测试环境。");
        }
      } catch (value) { onError(value); }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [currentTask, loadDevelopment, onError, onNotice, onRefresh]);

  async function start() {
    setBusy(true);
    try {
      saveUiStylePreference(project.id, uiStyleKey);
      const created = await api.startDevelopment(project.id, uiStyleKey);
      setTask(created);
      onNotice("工厂已经开始生成产品，关闭页面也不会丢失进度。");
      const refreshed = await api.project(project.id);
      onProjectChange(refreshed);
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  async function retry() {
    if (!currentTask) return;
    setBusy(true);
    try {
      const updated = await api.retryTask(currentTask.id);
      setTask(updated);
      onNotice("已从最后一个安全检查点重新开始。 ");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  const latestRun = runs[0];
  const planSteps = useMemo(() => {
    const raw = latestRun?.plan.steps;
    if (!Array.isArray(raw)) return Object.keys(STEP_LABELS);
    return raw.map((item) => {
      if (typeof item === "string") return friendlyDevelopmentStep(STEP_LABELS[item] ?? item);
      if (typeof item !== "object" || item === null || Array.isArray(item)) return "完成一项产品成果";
      const step = item as Record<string, unknown>;
      if (typeof step.product_language === "string") return friendlyDevelopmentStep(step.product_language);
      if (typeof step.key === "string") return friendlyDevelopmentStep(STEP_LABELS[step.key] ?? step.key);
      return "完成一项产品成果";
    });
  }, [latestRun]);
  const canStart = project.stage === "DEVELOPMENT" && (!currentTask || !["queued", "running"].includes(currentTask.status));
  const hasVerifiedCredential = credentials.some((item) => item.status === "verified" && (!item.project_id || item.project_id === project.id) && ["development", "both"].includes(item.scope));
  const realGenerationAvailable = capabilities?.ai_provider_mode === "verified" || hasVerifiedCredential;
  const localHtmlGenerationAvailable = ["trusted_mock", "trusted_local"].includes(
    capabilities?.generated_execution_mode ?? "",
  );
  const generationAvailable = realGenerationAvailable || localHtmlGenerationAvailable;
  const generationVerified = latestRun?.provider_verification === "verified";
  const generationIsSimulation = Boolean(latestRun && !generationVerified);
  const selectedUiStyle = UI_STYLE_OPTIONS.find((item) => item.key === uiStyleKey) ?? UI_STYLE_OPTIONS[0];
  const hasGeneratedHtml = Boolean(latestRun?.files.some((item) => item.path === "web/index.html"));
  const progressTitle = currentTask?.status === "succeeded"
    ? generationVerified ? "前后端测试环境已生成，可以开始验收" : hasGeneratedHtml ? "本地测试页面已生成，可以验收" : "测试环境仍待生成"
    : currentTask?.status === "failed" ? "生成已在安全位置暂停" : "工厂正在搭建你的产品";

  return (
    <>
      <StageIntro eyebrow="第 3 步 · 生成进度" title="工厂正在把方案变成真实产品" description="你只需要关注完成了哪些产品成果、什么时候可以体验。生成、检查和版本保存都由工厂在后台完成。" aside={<div className="safety-badge"><ShieldCheck size={20} /><div><strong>进度可恢复</strong><small>可以离开页面 · 随时回来继续</small></div></div>} />

      <section className={`reality-status-card ${generationIsSimulation || (!latestRun && capabilities && !realGenerationAvailable) ? "warning" : "verified"}`} aria-label="真实生成状态">
        <span>{generationVerified ? <ShieldCheck size={19} /> : <CircleAlert size={19} />}</span>
        <div><small>前后端生成能力</small><strong>{generationVerified ? "已使用经过验证的真实生成服务" : localHtmlGenerationAvailable ? "本地测试环境生成后端已就绪" : "当前尚未完成真实产品生成"}</strong><p>{generationIsSimulation ? "演示模板不能用于第三步上线测试环境，请连接真实代码生成器。" : !realGenerationAvailable && localHtmlGenerationAvailable ? "可以选择 UI 风格，并根据已确认 PRD 与低保真原型生成真实前后端测试环境。" : !realGenerationAvailable ? "需要先连接并验证真实生成服务；未连接前不会把模拟结果标记为真实产品。" : "真实生成服务已经可用，开始后会记录双 Handbook、检查结果和保存版本。"}</p></div>
        {!generationVerified && <button className="ghost-button" type="button" onClick={() => onNavigate("m2a")}>检查真实服务<ArrowRight size={15} /></button>}
      </section>

      {!task && !latestRun ? (
        <>
          {project.stage === "DEVELOPMENT" && generationAvailable && (changingUiStyle || !hasSavedUiStyle ? (
            <UiStylePicker value={uiStyleKey} onChange={(value) => { setUiStyleKey(value); setHasSavedUiStyle(true); saveUiStylePreference(project.id, value); }} />
          ) : (
            <section className="selected-ui-style-summary" aria-label="已确认的网页 UI 风格">
              <div><small>已从“确认方案”带入</small><strong>{selectedUiStyle.name}</strong><span>{selectedUiStyle.source} · {selectedUiStyle.note}</span></div>
              <button className="ghost-button" type="button" onClick={() => setChangingUiStyle(true)}>更换 UI 风格</button>
            </section>
          ))}
          <Panel><EmptyState title={project.stage === "DEVELOPMENT" ? generationAvailable ? "方案已确认，可以生成前后端测试环境" : "方案已确认，等待生成服务" : "完成产品方案后就能开始"} description={project.stage === "DEVELOPMENT" ? generationAvailable ? "工厂会读取确认的完整 PRD、低保真原型、产品方案和所选 UI 风格，生成前后端应用，运行上线前检查并保存可恢复版本。" : "先连接并验证生成服务，避免把体验数据当成正式产品。" : "请先确认产品范围、使用流程、费用和风险。"} action={canStart && generationAvailable ? <button className="primary-button" type="button" onClick={() => void start()} disabled={busy}><Play size={16} />{realGenerationAvailable ? "开始真实生成" : "生成测试环境"}</button> : undefined} /></Panel>
        </>
      ) : (
        <div className="development-grid product-progress-grid">
          <Panel className="development-progress-card">
            <div className="progress-hero"><div><span>产品生成进度</span><h2>{progressTitle}</h2><p>{currentTask?.status === "failed" ? "已经完成的成果和上一可用版本仍然保留，可以继续重试。" : generationIsSimulation ? "当前结果来自本地受控模板，不能作为上线测试环境；请连接真实代码生成服务后重新生成。" : "页面可以关闭，当前进度和中间成果会自动保存。"}</p></div><strong>{currentTask?.progress ?? (latestRun?.status === "succeeded" ? 100 : 0)}<small>%</small></strong></div>
            <div className="large-progress"><span style={{ width: `${currentTask?.progress ?? (latestRun?.status === "succeeded" ? 100 : 0)}%` }} /></div>
            <div className="development-steps">
              {planSteps.slice(0, 7).map((step, index) => {
                const progress = currentTask?.progress ?? 100;
                const complete = progress >= ((index + 1) / Math.min(planSteps.length, 7)) * 100;
                return <div key={`${step}-${index}`} className={complete ? "complete" : ""}><span>{complete ? <Check size={14} /> : index + 1}</span><p>{step}</p></div>;
              })}
            </div>
            <div className="task-facts"><KeyValue label="当前状态" value={<StatusPill status={currentTask?.status ?? latestRun?.status} />} /><KeyValue label="自动恢复" value={(currentTask?.max_attempts ?? 2) > 1 ? "已开启" : "准备中"} /><KeyValue label="进度保存" value={currentTask?.checkpoint && Object.keys(currentTask.checkpoint).length > 0 ? "已保存" : "自动保存中"} /></div>
            {hasGeneratedHtml && <div className="generated-html-result"><span><FileCode2 size={19} /></span><div><small>前后端测试环境已生成</small><strong>代码与运行配置已保存</strong><p>成果已保存在这个项目的独立工作区，并通过真实后端启动和接口检查。</p></div></div>}
            {currentTask?.status === "failed" && <button className="primary-button" type="button" onClick={() => void retry()} disabled={busy}><RotateCw size={16} />从上次进度继续</button>}
            {(currentTask?.status === "succeeded" || project.stage === "PREVIEW_REVIEW") && <button className="wide primary-button" type="button" onClick={() => onNavigate("m1d")}>{generationVerified ? "进入前后端测试环境" : hasGeneratedHtml ? "打开本地测试环境" : "查看当前测试环境"}<ArrowRight size={16} /></button>}
          </Panel>
        </div>
      )}

      {(workspace || latestRun) && <details className="implementation-details technical-evidence">
        <summary><span>实现说明</span><small>生成记录、保存版本和文件明细</small></summary>
        <div className="development-side">
          <Panel title="产品空间">
            {workspace ? <div className="workspace-facts"><KeyValue label="状态" value={<StatusPill status={workspace.status} />} /><KeyValue label="文件数量" value={`${workspace.file_count} 个`} /><KeyValue label="占用空间" value={formatBytes(workspace.size_bytes)} /><KeyValue label="保存版本" value={<code>{workspace.current_commit_ref?.slice(0, 10) ?? "准备中"}</code>} /></div> : <p className="muted-copy">产品空间正在准备。</p>}
          </Panel>
          <Panel title="工厂执行记录">
            {latestRun?.tools.length ? <div className="tool-timeline">{latestRun.tools.map((tool) => <div key={tool.id}><span className={tool.status}>{tool.status === "succeeded" ? <Check size={13} /> : tool.status === "failed" ? <CircleAlert size={13} /> : <Wrench size={13} />}</span><div><strong>{TOOL_LABELS[tool.tool_name] ?? tool.tool_name}</strong><small>{tool.side_effect === "none" ? "只读取，没有修改" : "已记录修改范围"}</small></div><StatusPill status={tool.status} /></div>)}</div> : <p className="muted-copy">产品开始生成后，这里会记录每项后台工作。</p>}
          </Panel>
        </div>
        {latestRun?.files.length > 0 && <Panel className="files-panel" title="生成文件" action={<span className="technical-label"><Code2 size={14} />技术明细</span>}>
          <div className="file-grid">{latestRun.files.map((file) => <article key={file.id}><span><FileCode2 size={18} /></span><div><strong>{file.path}</strong><p>{file.product_purpose}</p></div><small>{file.language}<br />{formatBytes(file.size_bytes)}</small></article>)}</div>
        </Panel>}
      </details>}
    </>
  );
}
