"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ExternalLink, RefreshCw, RotateCw } from "lucide-react";
import { api, isAppError } from "@/lib/api/client";
import type { DevelopmentRun, Preview, ProjectDetail, Task } from "@/lib/api/types";
import type { StageProps } from "../StagePanels";
import { UI_STYLE_OPTIONS, loadUiStylePreference, type UiStyleKey } from "../UiStylePicker";

type BuildViewState = "checking" | "generating" | "ready" | "failed";

function runUiStyle(run: DevelopmentRun | undefined): string {
  const context = run?.context;
  if (!context || typeof context !== "object" || Array.isArray(context)) return "";
  const productContext = context.product_context;
  if (!productContext || typeof productContext !== "object" || Array.isArray(productContext)) return "";
  const value = productContext as Record<string, unknown>;
  return typeof value.ui_style_key === "string" ? value.ui_style_key : "";
}

function projectPreviewToken(project: ProjectDetail): string | null {
  return project.preview?.token ?? project.preview_token ?? null;
}

export function M1DPreview({ project, onProjectChange, onRefresh, onError, onNotice, onNavigate }: StageProps) {
  const [desiredStyleKey] = useState<UiStyleKey>(() => loadUiStylePreference(project.id) ?? "pirsch-paper");
  const selectedStyle = UI_STYLE_OPTIONS.find((item) => item.key === desiredStyleKey) ?? UI_STYLE_OPTIONS[1];
  const [viewState, setViewState] = useState<BuildViewState>("checking");
  const [task, setTask] = useState<Task | null>(project.active_task ?? null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [accepting, setAccepting] = useState(false);
  const startInFlight = useRef(false);

  const showPreview = useCallback(async (token: string) => {
    const response = await api.preview(token);
    setPreview(response);
    setViewState("ready");
    setErrorMessage("");
  }, []);

  const startGeneration = useCallback(async () => {
    if (startInFlight.current) return;
    startInFlight.current = true;
    setViewState("generating");
    setErrorMessage("");
    try {
      const created = await api.startDevelopment(project.id, desiredStyleKey);
      setTask(created);
      const refreshed = await api.project(project.id);
      onProjectChange(refreshed);
    } catch (value) {
      startInFlight.current = false;
      setViewState("failed");
      setErrorMessage(isAppError(value) ? value.userMessage : "网页生成没有成功，请重新尝试。");
      onError(value);
    }
  }, [desiredStyleKey, onError, onProjectChange, project.id]);

  const synchronize = useCallback(async () => {
    setViewState("checking");
    try {
      const [detail, runResponse] = await Promise.all([
        api.project(project.id),
        api.developmentRuns(project.id).catch((value) => {
          if (isAppError(value) && (value.status === 404 || value.status === 409)) return { items: [] as DevelopmentRun[] };
          throw value;
        }),
      ]);
      const activeTask = detail.active_task ?? null;
      setTask(activeTask);
      if (activeTask && ["queued", "running"].includes(activeTask.status)) {
        setViewState("generating");
        return;
      }

      const latestRun = runResponse.items[0];
      const generatedStyle = runUiStyle(latestRun)
        || String(activeTask?.checkpoint?.ui_style_key ?? "pirsch-paper");
      const token = projectPreviewToken(detail);

      if (detail.stage === "DEVELOPMENT" || (detail.stage === "PREVIEW_REVIEW" && generatedStyle !== desiredStyleKey)) {
        await startGeneration();
        return;
      }
      if (detail.stage === "PAUSED" || activeTask?.status === "failed") {
        setViewState("failed");
        setErrorMessage("生成过程已经安全暂停，可以从上次进度继续。");
        return;
      }
      if (token) {
        await showPreview(token);
        return;
      }
      setViewState("failed");
      setErrorMessage("暂时没有找到可预览页面，请重新生成。");
    } catch (value) {
      setViewState("failed");
      setErrorMessage(isAppError(value) ? value.userMessage : "读取产品预览失败，请重新尝试。");
      onError(value);
    }
  }, [desiredStyleKey, onError, project.id, showPreview, startGeneration]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void synchronize(); }, 0);
    return () => window.clearTimeout(timer);
  }, [synchronize]);

  useEffect(() => {
    if (!task || !["queued", "running"].includes(task.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const updated = await api.task(task.id);
        setTask(updated);
        if (updated.status === "succeeded") {
          window.clearInterval(timer);
          startInFlight.current = false;
          const refreshed = await api.project(project.id);
          onProjectChange(refreshed);
          const token = projectPreviewToken(refreshed);
          if (!token) throw new Error("preview token missing after generation");
          await showPreview(token);
          onNotice(`“${selectedStyle.name}”风格网页已生成，可以直接体验。`);
        } else if (updated.status === "failed") {
          window.clearInterval(timer);
          startInFlight.current = false;
          setViewState("failed");
          setErrorMessage("生成过程已经安全暂停，可以从上次进度继续。");
        }
      } catch (value) {
        window.clearInterval(timer);
        startInFlight.current = false;
        setViewState("failed");
        setErrorMessage(isAppError(value) ? value.userMessage : "同步生成结果失败，请重新尝试。");
        onError(value);
      }
    }, 900);
    return () => window.clearInterval(timer);
  }, [onError, onNotice, onProjectChange, project.id, selectedStyle.name, showPreview, task]);

  async function retry() {
    if (task?.status === "failed") {
      setViewState("generating");
      setErrorMessage("");
      try {
        const retried = await api.retryTask(task.id);
        setTask(retried);
        return;
      } catch (value) {
        setViewState("failed");
        setErrorMessage(isAppError(value) ? value.userMessage : "恢复生成失败，请重试。");
        onError(value);
        return;
      }
    }
    startInFlight.current = false;
    await startGeneration();
  }

  async function accept() {
    if (!preview) return;
    setAccepting(true);
    try {
      await api.acceptPreview(preview.token, {
        core_flow_works: true,
        result_is_useful: true,
        history_persists: true,
        errors_are_understandable: true,
      });
      await onRefresh();
      onNavigate("m2b");
      onNotice("这版产品已确认，可以准备部署上线。");
    } catch (value) {
      onError(value);
    } finally {
      setAccepting(false);
    }
  }

  if (viewState === "checking" || viewState === "generating") {
    const progress = task?.progress ?? 0;
    return (
      <section className="build-preview-loading" aria-live="polite" aria-busy="true">
        <div className="build-loading-orbit" aria-hidden="true"><span /><i /></div>
        <small>{viewState === "checking" ? "正在读取确认方案" : "正在生成网页"}</small>
        <h1>{viewState === "checking" ? "正在准备你的产品预览" : `正在生成“${selectedStyle.name}”风格网页`}</h1>
        <p>系统会读取已确认 PRD、低保真方案和 UI 风格，生成并检查真实 HTML；完成后会自动打开可交互预览。</p>
        <div className="build-loading-track"><span style={{ width: `${Math.max(progress, viewState === "checking" ? 12 : 18)}%` }} /></div>
        <em>{viewState === "checking" ? "马上开始" : progress > 0 ? `${progress}%` : "生成中，请稍候"}</em>
        <div className="build-loading-skeleton" aria-hidden="true"><header><i /><i /><i /><b /></header><main><span /><strong /><p /><div><i /><i /></div></main></div>
      </section>
    );
  }

  if (viewState === "failed" || !preview) {
    return (
      <section className="build-preview-loading failed" role="alert">
        <div className="build-loading-orbit" aria-hidden="true"><RefreshCw size={22} /></div>
        <small>生成已暂停</small><h1>还没有得到可预览页面</h1><p>{errorMessage}</p>
        <button className="primary-button" type="button" onClick={() => void retry()}><RotateCw size={16} />继续生成</button>
      </section>
    );
  }

  const previewUrl = `${api.baseUrl.replace(/\/api\/v1$/, "")}${preview.url_path}`;
  return (
    <section className="build-preview-page" aria-label="可交互产品预览">
      <div className="build-preview-browser">
        <header>
          <span className="browser-dots" aria-hidden="true"><i /><i /><i /></span>
          <strong>{preview.config.title}</strong>
          <div><em>{selectedStyle.name}</em><a href={previewUrl} target="_blank" rel="noreferrer">独立打开<ExternalLink size={13} /></a></div>
        </header>
        <iframe key={preview.code_version.commit_ref} className="generated-html-frame" title={`${preview.config.title} HTML 产品预览`} src={previewUrl} />
      </div>
      <footer className="build-preview-actions">
        <button className="ghost-button" type="button" onClick={() => onNavigate("m1b")}><ArrowLeft size={15} />返回确认方案</button>
        <span>已按“{selectedStyle.name}”风格生成 · 可以直接点击体验</span>
        <button className="primary-button" type="button" disabled={accepting} onClick={() => void accept()}>{accepting ? "正在确认…" : "确认这版，准备部署"}<ArrowRight size={15} /></button>
      </footer>
    </section>
  );
}
