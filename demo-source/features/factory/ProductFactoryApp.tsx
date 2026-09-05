"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  CirclePlus,
  CloudOff,
  ClipboardCheck,
  FileUp,
  Menu,
  MonitorPlay,
  RefreshCw,
  Rocket,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { api, isAppError } from "@/lib/api/client";
import type { AppError, ProjectDetail, ProjectSummary, User } from "@/lib/api/types";
import { BossSteps } from "./BossSteps";
import { StagePanel } from "./StagePanels";
import {
  getCurrentPhaseIndex,
  getDefaultStageForPhase,
  getPhaseForStage,
  PRODUCT_PHASES,
  type ProductPhaseKey,
  type StageKey,
} from "./data";

type SessionState = "checking" | "signed_out" | "signed_in";

function readableError(value: unknown): AppError {
  if (isAppError(value)) return value;
  return {
    code: "NETWORK_ERROR",
    message: value instanceof Error ? value.message : "无法连接服务",
    userMessage: "暂时连接不到后端服务，请确认服务已启动后重试。",
    retryable: true,
  };
}

export function ProductFactoryApp() {
  const [session, setSession] = useState<SessionState>("checking");
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [activeStage, setActiveStage] = useState<StageKey>("m1a");
  const [activePhase, setActivePhase] = useState<ProductPhaseKey>("idea");
  const [busy, setBusy] = useState(false);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [error, setError] = useState<AppError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [mobileNav, setMobileNav] = useState(false);

  const showError = useCallback((value: unknown) => {
    setError(readableError(value));
    setNotice(null);
  }, []);

  const showNotice = useCallback((message: string) => {
    setNotice(message);
    setError(null);
    window.setTimeout(() => setNotice((current) => current === message ? null : current), 4200);
  }, []);

  const loadProjects = useCallback(async () => {
    const response = await api.projects();
    setProjects(response.items);
    return response.items;
  }, []);

  const openProject = useCallback(async (projectId: string, stage?: StageKey, phase?: ProductPhaseKey) => {
    setBusy(true);
    try {
      const detail = await api.project(projectId);
      setProject(detail);
      const nextPhase = phase
        ?? (stage ? getPhaseForStage(stage, detail.stage) : PRODUCT_PHASES[getCurrentPhaseIndex(detail.stage)]?.key)
        ?? "idea";
      const nextStage = stage ?? getDefaultStageForPhase(nextPhase, detail.stage);
      setActivePhase(nextPhase);
      setActiveStage(nextStage);
      const url = new URL(window.location.href);
      url.searchParams.set("project", projectId);
      url.searchParams.set("phase", nextPhase);
      url.searchParams.set("stage", nextStage);
      window.history.replaceState({}, "", url);
      setError(null);
    } catch (value) {
      showError(value);
    } finally {
      setBusy(false);
    }
  }, [showError]);

  const refreshProject = useCallback(async () => {
    if (!project) return;
    const detail = await api.project(project.id);
    setProject(detail);
    await loadProjects();
  }, [loadProjects, project]);

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      try {
        await api.health();
        if (active) setBackendOnline(true);
      } catch {
        if (active) setBackendOnline(false);
      }
      try {
        let auth: { user: User };
        try {
          auth = await api.me();
        } catch (value) {
          const normalized = readableError(value);
          const canResumeLocalCodex = normalized.status === 401
            && process.env.NEXT_PUBLIC_AUTH_MODE !== "demo";
          if (!canResumeLocalCodex) throw value;
          const resumed = await api.startCodexLogin();
          if (resumed.status !== "authenticated") throw value;
          auth = await api.me();
        }
        if (!active) return;
        setUser(auth.user);
        const items = await loadProjects();
        const params = new URLSearchParams(window.location.search);
        const requestedProject = params.get("project");
        const requestedStage = params.get("stage") as StageKey | null;
        const requestedPhase = params.get("phase") as ProductPhaseKey | null;
        if (requestedProject && items.some((item) => item.id === requestedProject)) {
          const validStage = ["m1a", "m1b", "m1c", "m1d", "m2a", "m2b", "m2c", "m3m4"].includes(requestedStage ?? "");
          const validPhase = PRODUCT_PHASES.some((item) => item.key === requestedPhase);
          await openProject(
            requestedProject,
            validStage ? requestedStage ?? undefined : undefined,
            validPhase ? requestedPhase ?? undefined : undefined,
          );
        } else if (items[0]) {
          await openProject(items[0].id);
        }
        if (active) setSession("signed_in");
      } catch (value) {
        if (!active) return;
        const normalized = readableError(value);
        setSession(normalized.status === 401 ? "signed_out" : "signed_out");
      }
    }
    void bootstrap();
    return () => { active = false; };
  }, [loadProjects, openProject]);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [project?.id, activeStage]);

  const chooseStage = useCallback((stage: StageKey) => {
    const phase = getPhaseForStage(stage, project?.stage);
    if (project && phase === "launch" && activePhase !== "launch") window.sessionStorage.setItem(`deployment-fresh-entry:${project.id}`, "new");
    setActiveStage(stage);
    setActivePhase(phase);
    setMobileNav(false);
    const url = new URL(window.location.href);
    url.searchParams.set("phase", phase);
    url.searchParams.set("stage", stage);
    window.history.replaceState({}, "", url);
  }, [activePhase, project]);

  const choosePhase = useCallback((phase: ProductPhaseKey) => {
    if (!project) return;
    if (phase === "launch" && !project.production_prepared && !["DEPLOYMENT", "DELIVERY"].includes(project.stage)) phase = "build";
    const stage = getDefaultStageForPhase(phase, project.stage);
    if (phase === "launch" && activePhase !== "launch") window.sessionStorage.setItem(`deployment-fresh-entry:${project.id}`, "new");
    setActivePhase(phase);
    setActiveStage(stage);
    setMobileNav(false);
    const url = new URL(window.location.href);
    url.searchParams.set("phase", phase);
    url.searchParams.set("stage", stage);
    window.history.replaceState({}, "", url);
  }, [activePhase, project]);

  const applyProjectChange = useCallback((nextProject: ProjectDetail) => {
    const phase = PRODUCT_PHASES[getCurrentPhaseIndex(nextProject.stage)]?.key ?? "idea";
    const stage = getDefaultStageForPhase(phase, nextProject.stage);
    setProject(nextProject);
    setActivePhase(phase);
    setActiveStage(stage);
    const url = new URL(window.location.href);
    url.searchParams.set("phase", phase);
    url.searchParams.set("stage", stage);
    window.history.replaceState({}, "", url);
  }, []);

  async function logout() {
    try { await api.logout(); } catch { /* A local cookie can already be expired. */ }
    setUser(null);
    setProjects([]);
    setProject(null);
    setSession("signed_out");
  }

  if (session === "checking") return <LoadingScreen backendOnline={backendOnline} />;
  if (session === "signed_out") {
    return <LoginScreen />;
  }

  return (
    <div className="app-shell">
      {error && (
        <div className="floating-alert error" role="alert">
          <CloudOff size={18} />
          <div><strong>这个操作没有完成</strong><span>{error.userMessage}</span></div>
          {error.retryable && <button type="button" onClick={() => window.location.reload()} aria-label="重新连接"><RefreshCw size={16} /></button>}
          <button type="button" onClick={() => setError(null)} aria-label="关闭提示"><X size={16} /></button>
        </div>
      )}
      {notice && (
        <div className="floating-alert success" role="status">
          <Check size={18} /><span>{notice}</span><button type="button" onClick={() => setNotice(null)} aria-label="关闭提示"><X size={16} /></button>
        </div>
      )}

      <Workspace
        project={project}
        projects={projects}
        user={user}
        activeStage={activeStage}
        activePhase={activePhase}
        mobileNav={mobileNav}
        busy={busy}
        onToggleNav={() => setMobileNav((value) => !value)}
        onChooseStage={chooseStage}
        onChoosePhase={choosePhase}
        onOpen={openProject}
        onCreate={async (name, idea) => {
          setBusy(true);
          try {
            const created = await api.createProject(name, idea);
            await loadProjects();
            setProject(created);
            setActivePhase("idea");
            setActiveStage("m1a");
            const url = new URL(window.location.href);
            url.searchParams.set("project", created.id);
            url.searchParams.set("phase", "idea");
            url.searchParams.set("stage", "m1a");
            window.history.replaceState({}, "", url);
            showNotice("项目已创建，第一轮需求问题已经准备好。");
          } catch (value) {
            showError(value);
            throw value;
          } finally {
            setBusy(false);
          }
        }}
        onDelete={async (projectId) => {
          setBusy(true);
          try {
            await api.deleteProject(projectId);
            const remainingProjects = await loadProjects();
            if (project?.id === projectId) {
              if (remainingProjects[0]) {
                await openProject(remainingProjects[0].id);
              } else {
                setProject(null);
                setActivePhase("idea");
                setActiveStage("m1a");
                const url = new URL(window.location.href);
                url.searchParams.delete("project");
                url.searchParams.delete("phase");
                url.searchParams.delete("stage");
                window.history.replaceState({}, "", url);
              }
            }
            showNotice("项目已删除。");
          } catch (value) {
            showError(value);
            throw value;
          } finally {
            setBusy(false);
          }
        }}
        onLogout={logout}
        onRefresh={refreshProject}
        onProjectChange={applyProjectChange}
        onError={showError}
        onNotice={showNotice}
      />
    </div>
  );
}

function DotLogo() {
  return (
    <span className="brand-mark dot-logo" aria-hidden="true">
      <span className="dot-logo-glyph">{Array.from({ length: 24 }, (_, index) => <i key={index} />)}</span>
    </span>
  );
}

function ChatGPTMark() {
  return (
    <svg viewBox="0 0 24 24" width="40" height="40" fill="currentColor" fillRule="evenodd" aria-hidden="true">
      <path d="M9.205 8.658v-2.26c0-.19.072-.333.238-.428l4.543-2.616c.619-.357 1.356-.523 2.117-.523 2.854 0 4.662 2.212 4.662 4.566 0 .167 0 .357-.024.547l-4.71-2.759a.797.797 0 0 0-.856 0l-5.97 3.473Zm10.609 8.8V12.06c0-.333-.143-.57-.429-.737l-5.97-3.473 1.95-1.118a.433.433 0 0 1 .476 0l4.543 2.617c1.309.76 2.189 2.378 2.189 3.948 0 1.808-1.07 3.473-2.76 4.163ZM7.802 12.703l-1.95-1.142c-.167-.095-.239-.238-.239-.428V5.899c0-2.545 1.95-4.472 4.591-4.472 1 0 1.927.333 2.712.928L8.23 5.067c-.285.166-.428.404-.428.737v6.898ZM12 15.128l-2.795-1.57v-3.33L12 8.658l2.795 1.57v3.33L12 15.128Zm1.796 7.23c-1 0-1.927-.332-2.712-.927l4.686-2.712c.285-.166.428-.404.428-.737v-6.898l1.974 1.142c.167.095.238.238.238.428v5.233c0 2.545-1.974 4.472-4.614 4.472Zm-5.637-5.303-4.544-2.617c-1.308-.761-2.188-2.378-2.188-3.948A4.482 4.482 0 0 1 4.21 6.327v5.423c0 .333.143.571.428.738l5.947 3.449-1.95 1.118a.432.432 0 0 1-.476 0Zm-.262 3.9c-2.688 0-4.662-2.021-4.662-4.519 0-.19.024-.38.047-.57l4.686 2.71c.286.167.571.167.856 0l5.97-3.448v2.26c0 .19-.07.333-.237.428l-4.543 2.616c-.619.357-1.356.523-2.117.523Zm5.899 2.83a5.947 5.947 0 0 0 5.827-4.756C22.287 18.339 24 15.84 24 13.296c0-1.665-.713-3.282-1.998-4.448.119-.5.19-.999.19-1.498 0-3.401-2.759-5.947-5.946-5.947-.642 0-1.26.095-1.88.31A5.962 5.962 0 0 0 10.205 0a5.947 5.947 0 0 0-5.827 4.757C1.713 5.447 0 7.945 0 10.49c0 1.666.713 3.283 1.998 4.448-.119.5-.19 1-.19 1.499 0 3.401 2.759 5.946 5.946 5.946.642 0 1.26-.095 1.88-.309a5.96 5.96 0 0 0 4.162 1.713Z" />
    </svg>
  );
}

function Brand() {
  return (
    <button className="brand" type="button" onClick={() => window.location.assign(window.location.pathname)} aria-label="返回产品首页">
      <DotLogo />
      <span><strong>点线面</strong><small>AI 产品交付平台</small></span>
    </button>
  );
}

function LoadingScreen({ backendOnline }: { backendOnline: boolean | null }) {
  return (
    <main className="center-screen">
      <div className="loading-orbit"><span /><span /><span /></div>
      <p>{backendOnline === false ? "正在重新连接产品工厂…" : "正在恢复你的产品进度…"}</p>
    </main>
  );
}

function LoginScreen() {
  const publicDemo = process.env.NEXT_PUBLIC_AUTH_MODE === "demo";
  const [loginState, setLoginState] = useState<"idle" | "starting" | "waiting">("idle");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("体验用户");
  const loginRun = useRef(0);

  async function startLogin() {
    if (loginState !== "idle") return;
    const currentRun = loginRun.current + 1;
    loginRun.current = currentRun;
    setLoginState("starting");
    setLoginError(null);

    const popup = window.open(
      "about:blank",
      "product-factory-codex-login",
      "popup,width=560,height=760,resizable=yes,scrollbars=yes",
    );
    if (!popup) {
      setLoginState("idle");
      setLoginError("授权窗口被浏览器拦截，请允许弹窗后重试。");
      return;
    }
    popup.document.title = "正在打开 ChatGPT 官方授权";
    popup.document.body.textContent = "正在打开 ChatGPT 官方授权…";

    try {
      const started = await api.startCodexLogin();
      if (started.status === "authenticated") {
        popup.close();
        window.location.reload();
        return;
      }
      if (started.status === "failed" || !started.auth_url) {
        throw new Error(started.error ?? "无法启动 ChatGPT 官方授权。");
      }
      popup.location.replace(started.auth_url);
      setLoginState("waiting");

      while (loginRun.current === currentRun) {
        await new Promise((resolve) => window.setTimeout(resolve, 1_000));
        const result = await api.codexLoginStatus(started.attempt_id);
        if (result.status === "authenticated") {
          if (!popup.closed) popup.close();
          window.location.reload();
          return;
        }
        if (result.status === "failed") {
          throw new Error(result.error ?? "ChatGPT 官方授权未完成。");
        }
      }
    } catch (value) {
      if (!popup.closed) popup.close();
      if (loginRun.current !== currentRun) return;
      const error = readableError(value);
      setLoginError(error.userMessage);
      setLoginState("idle");
    }
  }

  async function startDemoLogin() {
    if (loginState !== "idle") return;
    setLoginState("starting");
    setLoginError(null);
    try {
      await api.demoLogin(displayName.trim() || "体验用户");
      window.location.reload();
    } catch (value) {
      const error = readableError(value);
      setLoginError(error.userMessage);
      setLoginState("idle");
    }
  }

  return (
    <main className="login-layout">
      <section className="login-story">
        <Brand />
        <h1>不需要看代码<br /><em>看着产品长出来</em></h1>
        <div className="login-benefits">
          {[
            { icon: FileUp, title: "上传点子或 PRD", description: "用一句话或现有文档开始，Agent 帮你补全真正的产品需求。" },
            { icon: ClipboardCheck, title: "确认产品方案", description: "先看看产品准备怎么做，确认符合你的想法后，再开始生成产品。" },
            { icon: MonitorPlay, title: "生成与预览", description: "自动生成可运行产品，在真实预览中体验并直接提出修改。" },
            { icon: Rocket, title: "部署与上线", description: "获得线上地址、完整代码、测试报告和可下载的交付包。" },
          ].map(({ icon: Icon, title, description }, index) => (
            <article className="login-benefit-card" key={title}>
              <div className="login-benefit-meta"><span><Icon size={19} /></span><small>0{index + 1}</small></div>
              <h2>{title}</h2>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>
      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-auth-icon">{publicDemo ? <Sparkles size={32} /> : <ChatGPTMark />}</div>
        <header className="login-panel-header">
          <h2 id="login-title">{publicDemo ? "直接体验产品工厂" : "用你的 GPT 账号开始"}</h2>
          <p id="login-description">{publicDemo ? "创建一个独立体验空间，项目、PRD、方案和生成记录都会真实保存。" : "通过官方授权页面登录，继续管理和交付你的产品，点线面不会保存你的 ChatGPT 密码。"}</p>
        </header>
        <div className="login-permissions" aria-label="登录权限说明">
          <ul>
            <li><Check size={14} aria-hidden="true" /><span>{publicDemo ? "每次体验使用独立账号和项目空间" : "识别你的账号与登录状态"}</span></li>
            <li><Check size={14} aria-hidden="true" /><span>{publicDemo ? "需求和方案由已配置的真实模型生成" : "使用已授权的 GPT 能力执行产品任务"}</span></li>
            <li><Check size={14} aria-hidden="true" /><span>{publicDemo ? "数据写入持久化数据库，可刷新继续" : "不会读取或保存你的 ChatGPT 密码"}</span></li>
          </ul>
        </div>
        {publicDemo && (
          <label className="demo-login-field" htmlFor="demo-display-name">
            <span>体验昵称</span>
            <input id="demo-display-name" value={displayName} maxLength={80} onChange={(event) => setDisplayName(event.target.value)} />
          </label>
        )}
        <button
          className="primary-button wide gpt-login-button"
          type="button"
          disabled={loginState !== "idle"}
          onClick={() => { void (publicDemo ? startDemoLogin() : startLogin()); }}
          aria-describedby="login-description"
        >
          {loginState === "starting" && (publicDemo ? "正在创建体验空间…" : "正在打开官方授权…")}
          {loginState === "waiting" && "请在新窗口完成登录"}
          {loginState === "idle" && (publicDemo ? "立即体验产品" : "使用 GPT 账号登录")}
        </button>
        {loginError && <p className="login-error" role="alert">{loginError}</p>}
        <div className="login-trust-row">
          <ShieldCheck size={15} aria-hidden="true" />
          <span>{publicDemo ? "独立数据空间" : "官方安全授权"}</span>
          <i aria-hidden="true" />
          <span>可随时退出登录</span>
        </div>
      </section>
    </main>
  );
}

function CreateProjectDialog({ busy, onCreate, onClose }: {
  busy: boolean;
  onCreate: (name: string, idea: string) => Promise<void>;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [idea, setIdea] = useState("");
  const nameRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    nameRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [busy, onClose]);
  return (
    <div className="create-project-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
      <section className="inline-create-project create-project-dialog" role="dialog" aria-modal="true" aria-labelledby="inline-create-title">
        <button className="create-project-close" type="button" onClick={onClose} disabled={busy} aria-label="关闭创建项目"><X size={18} /></button>
          <span className="empty-project-kicker"><Sparkles size={16} />创建新项目</span>
          <h1 id="inline-create-title">创建你的新项目</h1>
          <p>填写项目名称和项目描述，平台将根据这些信息开始梳理需求。</p>
          <form onSubmit={(event) => { event.preventDefault(); void onCreate(name, idea).catch(() => undefined); }}>
            <label>项目名称<input ref={nameRef} value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：桌面番茄闹钟" minLength={1} maxLength={120} required /></label>
            <label>项目描述<textarea value={idea} onChange={(event) => setIdea(event.target.value)} placeholder="创建一个桌面番茄闹钟，帮助用户进行工作计时、保持专注并完成任务" minLength={3} maxLength={10000} required /></label>
            <div className="inline-create-actions">
              <button className="ghost-button" type="button" onClick={onClose} disabled={busy}>取消</button>
              <button className="primary-button" type="submit" disabled={busy}>{busy ? "正在创建…" : "创建项目"}<ArrowRight size={16} /></button>
            </div>
          </form>
      </section>
    </div>
  );
}

function EmptyProjectStart({ onCreate }: { onCreate: () => void }) {
  return (
    <section className="empty-project-onboarding direct-start-empty">
      <span className="empty-project-kicker"><Sparkles size={16} />你的第一个项目</span>
      <h1>先创建一个项目<br /><em>再开始梳理需求</em></h1>
      <p>输入产品想法或上传 PRD，平台会协助梳理需求、确认方案、生成预览并完成部署上线</p>
      <button className="primary-button" type="button" onClick={onCreate}><CirclePlus size={16} />创建项目</button>
    </section>
  );
}

function DeleteProjectDialog({ project, busy, onCancel, onConfirm }: {
  project: ProjectSummary;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => Promise<void>;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    cancelRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [busy, onCancel]);
  return (
    <div className="delete-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onCancel(); }}>
      <section className="delete-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-project-title">
        <span className="delete-dialog-icon" aria-hidden="true"><Trash2 size={20} /></span>
        <div>
          <h2 id="delete-project-title">删除“{project.name}”？</h2>
          <p>项目内容和当前进度将被永久删除，删除后无法恢复。</p>
        </div>
        <div className="delete-dialog-actions">
          <button ref={cancelRef} className="ghost-button" type="button" onClick={onCancel} disabled={busy}>取消</button>
          <button className="danger-button" type="button" onClick={() => { void onConfirm().catch(() => undefined); }} disabled={busy}>{busy ? "正在删除…" : "确认删除"}</button>
        </div>
      </section>
    </div>
  );
}

function Workspace({ project, projects, user, activeStage, activePhase, mobileNav, busy, onToggleNav, onChooseStage, onChoosePhase, onOpen, onCreate, onDelete, onLogout, onRefresh, onProjectChange, onError, onNotice }: {
  project: ProjectDetail | null;
  projects: ProjectSummary[];
  user: User | null;
  activeStage: StageKey;
  activePhase: ProductPhaseKey;
  mobileNav: boolean;
  busy: boolean;
  onToggleNav: () => void;
  onChooseStage: (stage: StageKey) => void;
  onChoosePhase: (phase: ProductPhaseKey) => void;
  onOpen: (id: string) => Promise<void>;
  onCreate: (name: string, idea: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onLogout: () => void;
  onRefresh: () => Promise<void>;
  onProjectChange: (project: ProjectDetail) => void;
  onError: (error: unknown) => void;
  onNotice: (message: string) => void;
}) {
  const persistedPhaseIndex = project ? getCurrentPhaseIndex(project.stage) : -1;
  const currentPhaseIndex = project?.production_prepared
    ? Math.max(persistedPhaseIndex, PRODUCT_PHASES.findIndex((item) => item.key === "launch"))
    : persistedPhaseIndex;
  const viewedPhaseIndex = PRODUCT_PHASES.findIndex((item) => item.key === activePhase);
  const projectId = project?.id;
  const [creatingProject, setCreatingProject] = useState(false);
  const [deletingProject, setDeletingProject] = useState<ProjectSummary | null>(null);
  const [expandedSidebarProjectId, setExpandedSidebarProjectId] = useState<string | null>(null);
  const sidebarCollapsed = Boolean(projectId && expandedSidebarProjectId !== projectId);
  const isCodexWorkbench = Boolean(project && activePhase === "idea" && activeStage === "m1a");
  const isFullHeightWorkbench = Boolean(isCodexWorkbench || (project && activePhase === "launch"));
  const accountName = user?.display_name.trim() || "Codex 用户";
  const accountInitial = accountName.slice(0, 1).toUpperCase();
  const startCreatingProject = () => {
    setCreatingProject(true);
    if (mobileNav) onToggleNav();
  };
  const openSidebarProject = async (projectId: string) => {
    setCreatingProject(false);
    await onOpen(projectId);
    if (mobileNav) onToggleNav();
  };
  return (
    <main className={`workspace-layout ${mobileNav ? "sidebar-open" : ""} ${project ? "project-workbench-mode" : ""} ${isCodexWorkbench ? "codex-workbench-mode" : ""} ${isFullHeightWorkbench ? "full-height-workbench-mode" : ""} ${project && !sidebarCollapsed ? "sidebar-expanded" : ""}`}>
      {mobileNav && <button className="sidebar-scrim" type="button" onClick={onToggleNav} aria-label="关闭阶段导航" />}
      {project && (
        <header className="workspace-progress-header">
          <BossSteps
            steps={PRODUCT_PHASES.map((item, index) => ({
              key: item.key,
              label: index === 0 ? "提出点子" : index === 1 ? "确认方案" : index === 2 ? "生成预览" : "部署上线",
            }))}
            activeKey={activePhase}
            completedBeforeIndex={currentPhaseIndex}
            onChange={onChoosePhase}
          />
        </header>
      )}
      <aside className={`factory-sidebar ${mobileNav ? "open" : ""}`}>
        <div className="sidebar-brand-row">
          <div className="sidebar-brand" aria-label="点线面">
            <DotLogo /><span><strong>点线面</strong></span>
          </div>
          {project && (
            <button
              className="workspace-nav-toggle"
              type="button"
              onClick={() => setExpandedSidebarProjectId((value) => value === projectId ? null : projectId ?? null)}
              aria-expanded={!sidebarCollapsed}
              aria-label={sidebarCollapsed ? "展开产品导航" : "收起产品导航"}
            >
              <span className="boss-icon boss-icon-sidecollapse" aria-hidden="true" />
            </button>
          )}
          <button className="sidebar-close" type="button" onClick={onToggleNav} aria-label="关闭导航"><X size={18} /></button>
        </div>

        <button className="sidebar-create-project" type="button" onClick={startCreatingProject} disabled={busy}>
          <CirclePlus size={15} />创建项目
        </button>

        <div className={`sidebar-project-list ${projects.length === 0 ? "empty" : ""}`} aria-label="全部项目列表">
          <small className="sidebar-section-label">全部项目</small>
          {projects.map((item) => (
            <div className="sidebar-project-row" key={item.id}>
              <button className={`sidebar-project-item ${project?.id === item.id ? "selected" : ""}`} type="button" onClick={() => void openSidebarProject(item.id)} disabled={busy} aria-current={project?.id === item.id ? "page" : undefined} title={`${item.name}：${item.idea}`}>
                <span className="sidebar-project-marker" aria-hidden="true"><span className="boss-icon boss-icon-file-cloud" /></span>
                <span className="sidebar-project-copy"><strong>{item.name}</strong><small>{item.idea || "暂无项目描述"}</small></span>
              </button>
              <button className="sidebar-project-delete" type="button" onClick={() => setDeletingProject(item)} disabled={busy} aria-label={`删除项目 ${item.name}`} title="删除项目"><Trash2 size={16} /></button>
            </div>
          ))}
          {projects.length === 0 && (
            <div className="sidebar-project-empty">
              <span className="sidebar-project-empty-art" aria-hidden="true" />
              <strong>暂无项目</strong>
              <small>请先前往创建项目</small>
            </div>
          )}
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-account">
            <div className="sidebar-profile">
              <span className="user-avatar" aria-hidden="true">{accountInitial}</span>
              <strong title={accountName}>{accountName}</strong>
            </div>
            <button type="button" onClick={onLogout} aria-label="退出登录" title="退出登录"><span className="boss-icon boss-icon-logout" aria-hidden="true" /></button>
          </div>
        </div>
      </aside>

      <section className="workspace-main">
        <div className="workspace-mobile-toolbar">
          <button className="mobile-menu" type="button" onClick={onToggleNav} aria-expanded={mobileNav} aria-label="打开阶段导航"><Menu size={20} /></button>
          <strong>{project?.name ?? "全部项目"}</strong>
          {project && <span>第 {viewedPhaseIndex + 1} 步</span>}
        </div>
        {project ? <>
          <StagePanel
            phase={activePhase}
            stage={activeStage}
            project={project}
            onProjectChange={onProjectChange}
            onRefresh={onRefresh}
            onError={onError}
            onNotice={onNotice}
            onNavigate={onChooseStage}
          />
        </> : <EmptyProjectStart onCreate={() => setCreatingProject(true)} />}
      </section>
      {creatingProject && (
        <CreateProjectDialog
          busy={busy}
          onCreate={async (name, idea) => {
            await onCreate(name, idea);
            setCreatingProject(false);
          }}
          onClose={() => setCreatingProject(false)}
        />
      )}
      {deletingProject && <DeleteProjectDialog project={deletingProject} busy={busy} onCancel={() => setDeletingProject(null)} onConfirm={async () => { await onDelete(deletingProject.id); setDeletingProject(null); }} />}
    </main>
  );
}
