"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ExternalLink, RefreshCw, RotateCw } from "lucide-react";
import { api, isAppError } from "@/lib/api/client";
import type { CostAuthorization, DevelopmentRun, Preview, ProjectDetail, Task } from "@/lib/api/types";
import type { StageProps } from "../StagePanels";
import { UI_STYLE_OPTIONS, loadUiStylePreference, type UiStyleKey } from "../UiStylePicker";
import { buildLowFidelityPrototypeContract } from "./SolutionVisualDecisionView";

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
  const [desiredStyleKey] = useState<UiStyleKey>(() => loadUiStylePreference(project.id) ?? "duolingo-sticker");
  const selectedStyle = UI_STYLE_OPTIONS.find((item) => item.key === desiredStyleKey) ?? UI_STYLE_OPTIONS[0];
  const [viewState, setViewState] = useState<BuildViewState>("checking");
  const [task, setTask] = useState<Task | null>(project.active_task ?? null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [accepting, setAccepting] = useState(false);
  const [pendingCostQuote, setPendingCostQuote] = useState<CostAuthorization | null>(null);
  const [preparingProduction, setPreparingProduction] = useState(false);
  const startInFlight = useRef(false);
  const confirmedPrd = project.latest_artifacts?.find((item) => item.type === "prd" && item.status === "confirmed")
    ?? project.latest_artifacts?.find((item) => item.type === "prd");
  const prototypeContract = useMemo(
    () => buildLowFidelityPrototypeContract(confirmedPrd?.content ?? {}),
    [confirmedPrd?.content],
  );

  const showPreview = useCallback(async (token: string) => {
    const response = await api.preview(token);
    setPreview(response);
    setViewState("ready");
    setErrorMessage("");
  }, []);

  const startGeneration = useCallback(async (confirmedAuthorizationId?: string) => {
    if (startInFlight.current) return;
    startInFlight.current = true;
    setViewState("generating");
    setErrorMessage("");
    try {
      let authorizationId = confirmedAuthorizationId;
      if (!authorizationId) {
        const quote = await api.quoteProjectCost(project.id, "development");
        if (quote.requires_confirmation && quote.status !== "confirmed") {
          setPendingCostQuote(quote);
          startInFlight.current = false;
          setViewState("failed");
          setErrorMessage("请确认本次预计用量后继续生成；确认前不会调用模型。");
          return;
        }
        authorizationId = quote.id;
      }
      setPendingCostQuote(null);
      const created = await api.startDevelopment(
        project.id,
        desiredStyleKey,
        prototypeContract,
        authorizationId,
      );
      setTask(created);
      const refreshed = await api.project(project.id);
      onProjectChange(refreshed);
    } catch (value) {
      startInFlight.current = false;
      setViewState("failed");
      setErrorMessage(isAppError(value) ? value.userMessage : "网页生成没有成功，请重新尝试。");
      onError(value);
    }
  }, [desiredStyleKey, onError, onProjectChange, project.id, prototypeContract]);

  const prepareProduction = useCallback(async (authorizationId: string) => {
    if (!preview) return;
    setPendingCostQuote(null);
    setPreparingProduction(true);
    setViewState("generating");
    try {
      const created = await api.prepareProduction(preview.token, authorizationId);
      setTask(created);
      if (created.status === "succeeded") {
        await onRefresh();
        onNavigate("m2b");
        onNotice("上线准备检查已通过，接下来连接云账号并确认费用。");
      }
    } catch (value) {
      setViewState("failed");
      setErrorMessage(isAppError(value) ? value.userMessage : "上线准备暂未完成，请重试。");
      onError(value);
    }
  }, [onError, onNavigate, onNotice, onRefresh, preview]);

  const confirmUsageAndGenerate = useCallback(async () => {
    if (!pendingCostQuote) return;
    setViewState("generating");
    setErrorMessage("");
    try {
      const confirmed = await api.confirmCostAuthorization(pendingCostQuote.id);
      startInFlight.current = false;
      if (preparingProduction) await prepareProduction(confirmed.id);
      else await startGeneration(confirmed.id);
    } catch (value) {
      startInFlight.current = false;
      setViewState("failed");
      setErrorMessage(isAppError(value) ? value.userMessage : "确认预计用量失败，请重新尝试。");
      onError(value);
    }
  }, [onError, pendingCostQuote, prepareProduction, preparingProduction, startGeneration]);

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
      if (activeTask?.checkpoint?.production_preparation) setPreparingProduction(true);
      if (activeTask && ["queued", "running"].includes(activeTask.status)) {
        setViewState("generating");
        return;
      }

      const latestRun = runResponse.items[0];
      const generatedStyle = runUiStyle(latestRun)
        || String(activeTask?.checkpoint?.ui_style_key ?? "duolingo-sticker");
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
      setErrorMessage("暂时没有找到可运行的测试环境，请重新生成。");
    } catch (value) {
      setViewState("failed");
      setErrorMessage(isAppError(value) ? value.userMessage : "读取产品测试环境失败，请重新尝试。");
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
          if (updated.checkpoint?.production_preparation) {
            onNavigate("m2b");
            onNotice("上线准备检查已通过，接下来连接云账号并确认费用。");
            return;
          }
          await showPreview(token);
          onNotice(`“${selectedStyle.name}”风格的前后端测试环境已生成。`);
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
  }, [onError, onNavigate, onNotice, onProjectChange, project.id, selectedStyle.name, showPreview, task]);

  async function retry() {
    if (preparingProduction && task?.status !== "failed") { await accept(); return; }
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
      setPreparingProduction(true);
      const quote = await api.quoteProjectCost(project.id, "development");
      if (quote.requires_confirmation && quote.status !== "confirmed") {
        setPendingCostQuote(quote);
        setViewState("failed");
        setErrorMessage("产品已确认。接下来检查完整功能、数据保存和用户隔离；自动补齐可能产生模型用量，请确认后继续。");
        return;
      }
      await prepareProduction(quote.id);
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
        <h1>{preparingProduction ? "正在检查并补齐上线准备" : viewState === "checking" ? "正在准备产品测试环境" : `正在生成“${selectedStyle.name}”风格的前后端应用`}</h1>
        <p>{preparingProduction ? "正在核对完整功能、前后端、数据保存和用户隔离。发现缺项会自动尝试修复并重新测试，通过后进入部署上线。" : "系统会读取已确认 PRD、低保真方案和 UI 风格，按照前后端 Handbook 生成真实业务代码，并通过测试、启动和接口检查。"}</p>
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
        <small>{preparingProduction ? "上线准备已暂停" : "生成已暂停"}</small><h1>{preparingProduction ? "检查尚未通过，暂不进入部署" : "还没有得到可运行的测试环境"}</h1><p>{errorMessage}</p>
        <button
          className="primary-button"
          type="button"
          onClick={() => void (pendingCostQuote ? confirmUsageAndGenerate() : retry())}
        >
          <RotateCw size={16} />{pendingCostQuote ? "确认用量并继续" : preparingProduction ? "继续检查和修复" : "继续生成"}
        </button>
      </section>
    );
  }

  const previewUrl = `${api.baseUrl.replace(/\/api\/v1$/, "")}${preview.url_path}`;
  return (
    <section className="build-preview-page" aria-label="产品上线测试环境">
      <div className="build-preview-browser">
        <header>
          <span className="browser-dots" aria-hidden="true"><i /><i /><i /></span>
          <strong>{preview.config.title}</strong>
          <div><em>{selectedStyle.name}</em><a href={previewUrl} target="_blank" rel="noreferrer">独立打开<ExternalLink size={13} /></a></div>
        </header>
        <iframe key={preview.code_version.commit_ref} className="generated-html-frame" title={`${preview.config.title} 前后端测试环境`} src={previewUrl} />
      </div>
      <footer className="build-preview-actions">
        <button className="ghost-button" type="button" onClick={() => onNavigate("m1b")}><ArrowLeft size={15} />返回确认方案</button>
        <span>已按双 Handbook 生成 · 当前连接真实后端测试环境</span>
        <button className="primary-button" type="button" disabled={accepting} onClick={() => void accept()}>{accepting ? "正在确认…" : "确认这版，准备部署"}<ArrowRight size={15} /></button>
      </footer>
    </section>
  );
}
