"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight, BadgeCheck, Bot, Check, CheckCircle2, ChevronRight, Circle, CloudUpload,
  Eye, EyeOff, FileCheck2, Globe2, KeyRound, LockKeyhole, MessageSquareText, RefreshCw,
  RotateCcw, SendHorizontal, Server, ShieldAlert, ShieldCheck, TerminalSquare, UserRound,
} from "lucide-react";
import { api, isAppError } from "@/lib/api/client";
import type { CloudCredential, Deployment, DeploymentAuthorization, PlatformCapabilities } from "@/lib/api/types";
import type { StageProps } from "../StagePanels";
import { StatusPill } from "../StageUi";
import { formatDate } from "../data";

type RouteKey = "new_account" | "needs_services" | "ready_account";
type GroupKey = "cloud" | "prepare" | "publish" | "verify";
type StepOwner = "你来完成" | "AI 自动处理" | "共同确认";
type DeploymentStep = {
  id: string;
  group: GroupKey;
  title: string;
  owner: StepOwner;
  summary: string;
  productActions: string[];
  aiActions: string[];
  outcome: string;
  billable?: boolean;
  sensitive?: boolean;
};
type GuideMessage = { id: string; role: "assistant" | "user"; body: string };

const GROUPS: Array<{ id: GroupKey; index: string; title: string; hint: string }> = [
  { id: "cloud", index: "01", title: "云平台准备", hint: "账号、实名、权限" },
  { id: "prepare", index: "02", title: "部署前自检", hint: "代码、CLI、环境" },
  { id: "publish", index: "03", title: "正式发布", hint: "网关、变量、地址" },
  { id: "verify", index: "04", title: "上线后验收", hint: "登录、数据、监控" },
];

const STEPS: DeploymentStep[] = [
  { id: "account", group: "cloud", title: "登录火山引擎账号", owner: "你来完成", summary: "先确认你能进入火山引擎控制台；没有账号就先注册。", productActions: ["打开火山引擎控制台并登录", "确认这是用于当前产品上线的账号"], aiActions: ["告诉你下一步该点哪里", "不代替你注册或完成实名认证"], outcome: "一个可以正常登录的云账号" },
  { id: "identity", group: "cloud", title: "完成实名认证", owner: "你来完成", summary: "个人认证够首版使用；如果要用 RDS PostgreSQL，再升级企业认证。", productActions: ["进入账号中心 → 实名认证", "完成个人或企业认证并回到这里"], aiActions: ["根据认证类型选择数据方案", "个人账号默认采用预留实例加云备份"], outcome: "云服务可以被正常开通" },
  { id: "access", group: "cloud", title: "准备安全授权", owner: "共同确认", summary: "AccessKey 是云账号的操作密码，只能走加密连接，不能粘贴到聊天里。", productActions: ["在访问控制中创建专用子账号", "生成一组只用于部署的密钥"], aiActions: ["验证账号身份和授权范围", "密钥加密保存、原文不回显"], outcome: "一组可撤销、仅用于部署的安全授权", sensitive: true },
  { id: "permissions", group: "cloud", title: "开通六项服务权限", owner: "你来完成", summary: "函数服务、对象存储、数据库、镜像、日志和私有网络需要逐项授权。", productActions: ["为部署子账号添加六项 FullAccess 权限", "遇到 AccessDenied 时截图发到左侧"], aiActions: ["逐服务调用接口验证权限", "只报告缺少的权限，不扩大授权范围"], outcome: "部署所需服务均可访问" },
  { id: "mvp", group: "prepare", title: "确认 MVP 已经验收", owner: "共同确认", summary: "只部署已经生成、测试通过并由你确认的预览版本。", productActions: ["确认上一阶段预览可以真实操作", "确认核心流程与 PRD 一致"], aiActions: ["锁定已验收的代码版本", "保留上一可用版本用于回退"], outcome: "一个不可被悄悄替换的上线版本" },
  { id: "online_code", group: "prepare", title: "适配线上运行环境", owner: "AI 自动处理", summary: "数据库和文件不能继续写在只读目录，密钥也不能跟代码一起打包。", productActions: ["确认登录方式、预算和数据留存要求"], aiActions: ["数据库路径切到 /tmp 或云数据库", "排除 .env、.venv、data 和 .vefaas", "补登录隔离、备份、trace_id 与错误监控"], outcome: "一份可以安全上线的代码包" },
  { id: "tools", group: "prepare", title: "安装部署工具", owner: "AI 自动处理", summary: "安装 veFaaS CLI 和官方 AI Skill，再完成授权登录。", productActions: ["只在系统安全窗口中确认授权"], aiActions: ["确认 CLI 版本不低于 0.2.7", "更新 veFaaS Skill", "运行 login --check 与 doctor"], outcome: "AI 可以按官方规则执行部署" },
  { id: "inspect", group: "prepare", title: "检查项目与启动方式", owner: "AI 自动处理", summary: "识别前后端目录、框架、端口和启动命令，避免上线后打不开。", productActions: ["无需理解启动命令；只需确认检查结果"], aiActions: ["运行 vefaas inspect", "FastAPI 显式使用 python -m uvicorn", "Next.js 使用 standalone 产物"], outcome: "明确的后端和前端部署配置" },
  { id: "gateway", group: "publish", title: "确认或创建 API 网关", owner: "共同确认", summary: "网关是产品的公网大门；默认选 Serverless、公网、北京地域。", productActions: ["如果没有网关，按指引创建 Serverless 网关", "创建前确认按量计费"], aiActions: ["先查询是否已有可用网关", "优先复用，不重复创建收费资源"], outcome: "一个可给前后端复用的 HTTPS 入口", billable: true },
  { id: "environment", group: "publish", title: "先配置线上环境变量", owner: "AI 自动处理", summary: "必须在首次发布前配置 ENV=prod 和 DATABASE_URL，否则应用会写入只读目录并崩溃。", productActions: ["确认邀请码和需要接入的模型/语音服务"], aiActions: ["密钥只写入线上环境变量", "确认 sqlite:////tmp/data/app.db", "只检查键名，不回显密钥值"], outcome: "应用首次启动所需配置完整", sensitive: true },
  { id: "backend", group: "publish", title: "发布后端应用", owner: "AI 自动处理", summary: "首次发布不带预留实例；部署完成后再单独设置，避免函数尚无版本时报错。", productActions: ["正式执行前确认发布位置、权限和费用"], aiActions: ["显式指定启动命令与 8000 端口", "滚动发布先查状态，不反复重试"], outcome: "一个可访问的后端 HTTPS 地址", billable: true },
  { id: "reserved", group: "publish", title: "设置一个预留实例", owner: "AI 自动处理", summary: "让后端至少保留一个常驻实例，降低 /tmp 数据因缩容被回收的风险。", productActions: ["确认预留实例会产生持续费用"], aiActions: ["部署成功后再执行 min 1", "记录函数 ID 和变更结果"], outcome: "早期数据不会因空闲缩容立即消失", billable: true },
  { id: "frontend", group: "publish", title: "单独发布前端网页", owner: "AI 自动处理", summary: "前端与后端是两个独立应用；前端通过同源代理访问后端。", productActions: ["无需配置跨域；只需验收正式入口"], aiActions: ["构建 standalone 产物", "构建时注入后端地址", "发布 3000 端口前端应用"], outcome: "一个给真实用户使用的网页入口" },
  { id: "address", group: "publish", title: "打开线上地址验证", owner: "共同确认", summary: "是否上线成功，以 HTTPS 网址能不能真实打开为准，不只看控制台状态。", productActions: ["点击线上地址走一遍核心流程", "记录无法打开时的页面现象"], aiActions: ["验证首页和 /api/*", "保留上一可用版本用于回滚"], outcome: "一个被真实打开验证过的线上地址" },
  { id: "auth", group: "verify", title: "验证登录与数据隔离", owner: "AI 自动处理", summary: "无 token 拒绝、错误邀请码拒绝、正确邀请码可用；A 用户看不到 B 用户数据。", productActions: ["保管并分发正式邀请码"], aiActions: ["自动验证三条登录链路", "跨账号访问必须返回 403"], outcome: "每个用户只能访问自己的数据" },
  { id: "persistence", group: "verify", title: "验证数据可恢复", owner: "AI 自动处理", summary: "数据库定期备份到对象存储，实例重建时可以自动恢复。", productActions: ["确认可以接受的最大数据回退时间"], aiActions: ["验证备份已经写入", "执行一次启动恢复检查"], outcome: "刷新、重启和故障后数据仍可找回" },
  { id: "storage", group: "verify", title: "验证文件对象存储", owner: "AI 自动处理", summary: "音频和图片不放在实例本地目录，换设备和实例重建后仍能读取。", productActions: ["确认文件保存时长和删除规则"], aiActions: ["验证 TOS 写入与读取", "使用 s3v4 和 virtual addressing"], outcome: "业务数据与大文件分开保存" },
  { id: "monitor", group: "verify", title: "验证日志与错误通知", owner: "AI 自动处理", summary: "每个请求有 trace_id，错误能通知；日志不记录密钥和敏感原文。", productActions: ["确认错误通知发到哪里"], aiActions: ["触发一次可控错误验证告警", "检查 trace_id 能串联请求"], outcome: "出问题时能定位、能收到通知" },
  { id: "acceptance", group: "verify", title: "完成上线验收", owner: "你来完成", summary: "在电脑和手机上完成最后一轮真实验收，再领取线上地址与交付物。", productActions: ["登录、核心流程、刷新和换设备各走一遍", "确认手机端可用", "通过后进入交付内容"], aiActions: ["更新 README 和部署记录", "整理访问地址、邀请码和验收清单"], outcome: "线上地址、登录方式和完整交付内容" },
];

const ROUTES: Array<{ key: RouteKey; label: string; description: string; firstStep: string }> = [
  { key: "new_account", label: "还没有云账号", description: "从注册和实名认证开始", firstStep: "account" },
  { key: "needs_services", label: "有账号，没开服务", description: "先检查授权和网关", firstStep: "permissions" },
  { key: "ready_account", label: "账号和服务都有", description: "直接从项目自检开始", firstStep: "inspect" },
];
const INITIAL_MESSAGES: GuideMessage[] = [
  { id: "welcome", role: "assistant", body: "我已读取《AI Agent 产品上线部署手册》。接下来一次只带你完成一个动作，涉及计费和正式发布时一定先让你确认。" },
  { id: "route-question", role: "assistant", body: "先告诉我：你的火山引擎账号现在到哪一步？" },
];

function deploymentReply(input: string, current: DeploymentStep): string {
  if (/(密钥|AK|SK|AccessKey)/i.test(input)) return "请不要把密钥发在聊天里。右侧到“准备安全授权”时，只能通过加密连接；聊天、前端和交付文件都不会保存密钥原文。";
  if (/(费用|收费|多少钱|预算)/.test(input)) return "API 网关和预留实例可能产生费用。真正创建资源前，右侧会先显示发布位置、授权范围和费用；没有你的确认不会执行。";
  if (/(失败|报错|滚动|打不开)/.test(input)) return "先不要反复点部署。把现象或截图发给我，我会先查发布记录和访问地址，再决定等待、中止滚动发布或回退。";
  return `收到。当前先完成“${current.title}”。右侧已把你需要做的动作和 AI 会做的动作分开列出。`;
}

export function M2BDeployment({ project, onRefresh, onError, onNotice, onNavigate }: StageProps) {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [credential, setCredential] = useState<CloudCredential | null>(null);
  const [authorization, setAuthorization] = useState<DeploymentAuthorization | null>(null);
  const [capabilities, setCapabilities] = useState<PlatformCapabilities | null>(null);
  const [accessKey, setAccessKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [showSecrets, setShowSecrets] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deploymentDisabled, setDeploymentDisabled] = useState(false);
  const [route, setRoute] = useState<RouteKey | null>(null);
  const [selectedStepId, setSelectedStepId] = useState("account");
  const [completedStepIds, setCompletedStepIds] = useState<string[]>([]);
  const [messages, setMessages] = useState<GuideMessage[]>(INITIAL_MESSAGES);
  const [messageDraft, setMessageDraft] = useState("");
  const [guideHydrated, setGuideHydrated] = useState(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    try {
      const [deploymentResult, runtime, credentialResult, authorizationResult] = await Promise.all([
        api.deployments(project.id), api.capabilities(), api.cloudCredentials(project.id), api.deploymentAuthorizations(project.id),
      ]);
      setDeployments(deploymentResult.items);
      setCapabilities(runtime);
      setCredential(credentialResult.items.find((item) => !["revoked", "expired"].includes(item.status)) ?? null);
      setAuthorization(authorizationResult.items.find((item) => !["expired", "consumed"].includes(item.status)) ?? authorizationResult.items[0] ?? null);
    } catch (value) { if (!(isAppError(value) && value.status === 404)) onError(value); }
  }, [onError, project.id]);

  useEffect(() => { const timer = window.setTimeout(() => { void load(); }, 0); return () => window.clearTimeout(timer); }, [load]);
  useEffect(() => {
    const key = `deployment-guide:${project.id}`;
    const timer = window.setTimeout(() => {
      try {
        const raw = window.localStorage.getItem(key);
        if (raw) {
          const saved = JSON.parse(raw) as { route?: RouteKey; selectedStepId?: string; completedStepIds?: string[]; messages?: GuideMessage[] };
          if (saved.route) setRoute(saved.route);
          if (saved.selectedStepId && STEPS.some((step) => step.id === saved.selectedStepId)) setSelectedStepId(saved.selectedStepId);
          if (Array.isArray(saved.completedStepIds)) setCompletedStepIds(saved.completedStepIds.filter((id) => STEPS.some((step) => step.id === id)));
          if (Array.isArray(saved.messages) && saved.messages.length) setMessages(saved.messages.slice(-24));
        }
      } catch { window.localStorage.removeItem(key); }
      setGuideHydrated(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [project.id]);
  useEffect(() => {
    if (guideHydrated) window.localStorage.setItem(`deployment-guide:${project.id}`, JSON.stringify({ route, selectedStepId, completedStepIds, messages: messages.slice(-24) }));
  }, [completedStepIds, guideHydrated, messages, project.id, route, selectedStepId]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ block: "nearest" }); }, [messages]);

  const latest = deployments[0];
  const previewAccepted = Boolean(project.preview_accepted || ["DEPLOYMENT", "DELIVERY"].includes(project.stage));
  const realDeploymentAvailable = Boolean(capabilities?.deployment_enabled && capabilities.deployment_mode === "external");
  const providerLabel = capabilities?.deployment_provider === "volcano_engine" ? "火山引擎 veFaaS" : capabilities?.deployment_provider ?? "发布服务读取中";
  const regionLabel = capabilities?.deployment_region === "cn-beijing" ? "华北 2（北京）" : capabilities?.deployment_region ?? "位置读取中";
  const completed = useMemo(() => {
    const ids = new Set(completedStepIds);
    if (previewAccepted) ids.add("mvp");
    if (credential) ids.add("access");
    if (authorization) ids.add("gateway");
    if (latest) ids.add("backend");
    if (latest?.deployment_url) ids.add("address");
    return ids;
  }, [authorization, completedStepIds, credential, latest, previewAccepted]);
  const selectedStep = STEPS.find((step) => step.id === selectedStepId) ?? STEPS[0];
  const selectedGroupIndex = GROUPS.findIndex((group) => group.id === selectedStep.group);
  const completedCount = STEPS.filter((step) => completed.has(step.id)).length;
  const guidePercent = Math.round((completedCount / STEPS.length) * 100);
  const estimatedCost = authorization?.estimated_cost ?? {};
  const costLabel = estimatedCost.pricing_configured && typeof estimatedCost.amount_minor === "number"
    ? `${estimatedCost.currency === "CNY" ? "¥" : String(estimatedCost.currency ?? "")} ${(Number(estimatedCost.amount_minor) / 100).toFixed(2)}` : "尚未返回真实金额";

  function appendMessages(...items: Array<Omit<GuideMessage, "id">>) {
    setMessages((current) => [...current, ...items.map((item, index) => ({ ...item, id: `${Date.now()}-${index}` }))].slice(-24));
  }
  function chooseRoute(routeKey: RouteKey) {
    const choice = ROUTES.find((item) => item.key === routeKey) ?? ROUTES[0];
    setRoute(routeKey); setSelectedStepId(choice.firstStep);
    const reply = routeKey === "new_account" ? "好，我们从账号和实名认证开始。你不用先理解云服务名词。" : routeKey === "needs_services" ? "好，我们先核对权限和网关，不会重复创建收费资源。" : "好，我先检查项目、CLI 和现有云资源，不会跳过费用和数据安全验证。";
    appendMessages({ role: "user", body: choice.label }, { role: "assistant", body: reply });
  }
  function resetGuide() { setRoute(null); setSelectedStepId("account"); setCompletedStepIds([]); setMessages(INITIAL_MESSAGES); }
  function markCurrentComplete() {
    if (!completed.has(selectedStep.id)) setCompletedStepIds((items) => [...items, selectedStep.id]);
    const currentIndex = STEPS.findIndex((step) => step.id === selectedStep.id);
    const next = STEPS.slice(currentIndex + 1).find((step) => !completed.has(step.id));
    appendMessages({ role: "user", body: `“${selectedStep.title}”已完成` }, { role: "assistant", body: next ? `已记录。下一步是“${next.title}”，右侧已打开操作说明。` : "上线流程已走完。请进入交付内容。" });
    if (next) setSelectedStepId(next.id);
  }
  function sendMessage() {
    const content = messageDraft.trim(); if (!content) return; setMessageDraft("");
    appendMessages({ role: "user", body: content }, { role: "assistant", body: route ? deploymentReply(content, selectedStep) : "请先点击上面的三个账号状态之一，我会把右侧流程定位到对应步骤。" });
  }

  async function connectCloud() {
    setBusy(true);
    try {
      const created = await api.connectCloudCredential(project.id, accessKey.trim(), secretKey.trim());
      setCredential(created); setAccessKey(""); setSecretKey("");
      onNotice("火山引擎凭证已加密保存，原文已从页面清空。");
      appendMessages({ role: "assistant", body: "云账号已通过加密通道连接。下一步先检查权限，不会直接创建资源。" });
    } catch (value) { if (isAppError(value) && value.code === "DEPLOYMENT_DISABLED") setDeploymentDisabled(true); onError(value); }
    finally { setBusy(false); }
  }
  async function quote() {
    if (!credential) return; setBusy(true);
    try { const result = await api.quoteDeployment(project.id, credential.id, capabilities?.deployment_region); setAuthorization(result); onNotice("本次上线的权限和费用范围已经准备好，请检查后确认。"); }
    catch (value) { onError(value); } finally { setBusy(false); }
  }
  async function confirmAndDeploy() {
    if (!authorization) return; setBusy(true);
    try {
      const confirmed = authorization.status === "confirmed" ? authorization : await api.confirmDeployment(authorization.id);
      setAuthorization(confirmed); await api.startDeployment(project.id, confirmed.id); await load(); await onRefresh(); setSelectedStepId("backend");
      onNotice("产品已经开始发布，进度会自动保存。"); appendMessages({ role: "assistant", body: "正式发布已经开始。如果中途失败，上一可用版本仍然保留。" });
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  const actualState = latest?.status === "succeeded" ? "已真实上线" : latest?.status === "simulated" ? "只完成发布演练，没有创建线上资源" : ["queued", "running"].includes(latest?.status ?? "") ? "正在发布" : realDeploymentAvailable ? "真实发布已就绪" : "流程演练模式";

  return (
    <section className="deployment-workbench" aria-label="上线部署工作台">
      <aside className="deployment-assistant-pane">
        <header className="deployment-chat-header">
          <span className="deployment-bot-avatar"><Bot size={19} /></span>
          <div><strong>上线助手</strong><small><i />按部署手册逐步引导</small></div>
          {route && <button type="button" onClick={resetGuide}>重选起点</button>}
        </header>
        <div className="deployment-chat-thread" aria-live="polite">
          <div className="deployment-context-card"><FileCheck2 size={16} /><div><strong>已读取上线部署手册</strong><small>默认路线：火山引擎 + veFaaS</small></div></div>
          {messages.map((message) => <article className={message.role} key={message.id}><span aria-hidden="true">{message.role === "assistant" ? <Bot size={15} /> : <UserRound size={15} />}</span><p>{message.body}</p></article>)}
          {!route && <div className="deployment-route-options" aria-label="选择云账号状态">{ROUTES.map((item) => <button type="button" key={item.key} onClick={() => chooseRoute(item.key)}><span><strong>{item.label}</strong><small>{item.description}</small></span><ChevronRight size={16} /></button>)}</div>}
          {route && <div className="deployment-chat-current"><small>当前带你完成</small><button type="button" onClick={() => setSelectedStepId(selectedStep.id)}>{selectedStep.title}<ArrowRight size={14} /></button></div>}
          <div ref={chatEndRef} />
        </div>
        <form className="deployment-chat-composer" onSubmit={(event) => { event.preventDefault(); sendMessage(); }}>
          <div className="deployment-secret-reminder"><LockKeyhole size={13} />不要在聊天中发送 AK/SK 或其他密钥</div>
          <div><textarea value={messageDraft} onChange={(event) => setMessageDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(); } }} rows={2} placeholder="描述你看到的页面、报错或问题…" /><button type="submit" disabled={!messageDraft.trim()} aria-label="发送消息"><SendHorizontal size={16} /></button></div>
        </form>
      </aside>

      <div className="deployment-process-pane">
        <header className="deployment-process-header">
          <div><span className="deployment-process-kicker">第 4 步 · 部署上线</span><h1>把已确认的产品安全发布到线上</h1><p>每一步都说明谁来做、会产生什么结果。涉及费用、密钥和正式发布时，必须由你确认。</p></div>
          <div className="deployment-runtime-status"><span className={realDeploymentAvailable ? "live" : "practice"}>{realDeploymentAvailable ? <Globe2 size={15} /> : <ShieldAlert size={15} />}{actualState}</span><small>{providerLabel} · {regionLabel}</small></div>
        </header>
        <div className="deployment-progress-summary">
          <div><span>上线流程</span><strong>{completedCount}<small> / {STEPS.length} 项已确认</small></strong></div>
          <div className="deployment-progress-track" aria-label={`上线流程已确认 ${guidePercent}%`}><span style={{ width: `${guidePercent}%` }} /></div>
          <p>{previewAccepted ? <><CheckCircle2 size={15} />生成预览已确认，当前可以进入部署准备</> : <><Circle size={15} />请先确认生成预览，再开始真实发布</>}</p>
        </div>
        <nav className="deployment-phase-track" aria-label="部署阶段">
          {GROUPS.map((group, index) => {
            const groupSteps = STEPS.filter((step) => step.group === group.id); const groupDone = groupSteps.every((step) => completed.has(step.id)); const active = group.id === selectedStep.group;
            return <button type="button" className={`${active ? "active" : ""} ${groupDone ? "done" : ""}`} key={group.id} onClick={() => setSelectedStepId(groupSteps.find((step) => !completed.has(step.id))?.id ?? groupSteps[0].id)}><span>{groupDone ? <Check size={15} /> : group.index}</span><div><strong>{group.title}</strong><small>{group.hint}</small></div>{index < GROUPS.length - 1 && <i aria-hidden="true" />}</button>;
          })}
        </nav>
        <div className="deployment-process-body">
          <aside className="deployment-step-list" aria-label="当前阶段步骤">
            <small>{GROUPS[selectedGroupIndex]?.title}</small>
            {STEPS.filter((step) => step.group === selectedStep.group).map((step, index) => <button type="button" className={`${step.id === selectedStep.id ? "active" : ""} ${completed.has(step.id) ? "done" : ""}`} key={step.id} onClick={() => setSelectedStepId(step.id)}><span>{completed.has(step.id) ? <Check size={13} /> : index + 1}</span><div><strong>{step.title}</strong><small>{step.owner}</small></div><ChevronRight size={14} /></button>)}
          </aside>
          <article className="deployment-step-detail">
            <header>
              <div className="deployment-owner-row"><span className={selectedStep.owner === "AI 自动处理" ? "ai" : selectedStep.owner === "你来完成" ? "human" : "shared"}>{selectedStep.owner === "AI 自动处理" ? <TerminalSquare size={14} /> : selectedStep.owner === "你来完成" ? <UserRound size={14} /> : <MessageSquareText size={14} />}{selectedStep.owner}</span>{selectedStep.billable && <em><ShieldAlert size={13} />创建资源前需确认费用</em>}{selectedStep.sensitive && <em><LockKeyhole size={13} />密钥不进聊天</em>}</div>
              <h2>{selectedStep.title}</h2><p>{selectedStep.summary}</p>
            </header>
            <div className="deployment-action-columns">
              <section><h3><UserRound size={15} />你需要做</h3><ul>{selectedStep.productActions.map((item) => <li key={item}><Circle size={12} />{item}</li>)}</ul></section>
              <section><h3><Bot size={15} />AI 会自动做</h3><ul>{selectedStep.aiActions.map((item) => <li key={item}><CheckCircle2 size={13} />{item}</li>)}</ul></section>
            </div>
            <div className="deployment-step-outcome"><BadgeCheck size={18} /><div><small>完成后你会得到</small><strong>{selectedStep.outcome}</strong></div></div>

            {selectedStep.id === "access" && <div className="deployment-inline-control">{!realDeploymentAvailable ? <div className="deployment-honest-state"><ShieldAlert size={17} /><div><strong>当前平台未启用真实发布适配器</strong><p>现在只能走查流程，不会收集你的真实 AK/SK，也不会创建云资源。启用受信任适配器后，这里才会开放加密连接。</p></div></div> : !credential ? <form className="deployment-credential-form" onSubmit={(event) => { event.preventDefault(); void connectCloud(); }}><label>发布账号标识<input type={showSecrets ? "text" : "password"} value={accessKey} onChange={(event) => setAccessKey(event.target.value)} minLength={8} autoComplete="off" /></label><label>发布账号密钥<span><input type={showSecrets ? "text" : "password"} value={secretKey} onChange={(event) => setSecretKey(event.target.value)} minLength={8} autoComplete="off" /><button type="button" onClick={() => setShowSecrets((value) => !value)} aria-label="显示或隐藏授权信息">{showSecrets ? <EyeOff size={15} /> : <Eye size={15} />}</button></span></label><p><LockKeyhole size={13} />凭证只通过后端加密保存，原文不会进入聊天、前端文件或交付包。</p><button className="primary-button" type="submit" disabled={busy || accessKey.length < 8 || secretKey.length < 8}><CloudUpload size={15} />安全连接云账号</button></form> : <div className="deployment-connected"><CheckCircle2 size={18} /><div><strong>云账号已安全连接</strong><small>{credential.masked_access_key} · {credential.service}</small></div><StatusPill status={credential.status} /></div>}</div>}

            {selectedStep.id === "backend" && <div className="deployment-inline-control">{!realDeploymentAvailable ? <div className="deployment-honest-state"><ShieldAlert size={17} /><div><strong>当前不能生成真实线上地址</strong><p>后端目前只支持发布演练。页面保留完整流程，但不会把模拟结果标记为正式产品。</p></div></div> : !credential ? <button className="ghost-button wide" type="button" onClick={() => setSelectedStepId("access")}><KeyRound size={15} />先安全连接云账号<ArrowRight size={15} /></button> : !authorization ? <button className="primary-button wide" type="button" onClick={() => void quote()} disabled={busy}><ShieldCheck size={15} />检查权限与真实费用<ArrowRight size={15} /></button> : <div className="deployment-authorization"><div><span>发布位置<strong>{providerLabel} · {regionLabel}</strong></span><span>预计费用<strong>{costLabel}</strong></span><span>确认有效期<strong>{formatDate(authorization.expires_at)}</strong></span></div><p><ShieldAlert size={14} />确认只对当前产品和本次发布有效；失败时上一可用版本仍保留。</p><button className="primary-button wide" type="button" disabled={busy} onClick={() => void confirmAndDeploy()}>{busy ? "正在开始发布…" : "确认以上信息，正式发布"}<ArrowRight size={15} /></button></div>}</div>}

            {selectedStep.id === "address" && latest && <div className="deployment-inline-control"><div className="deployment-live-result"><span><Server size={18} /></span><div><small>{latest.status === "simulated" ? "发布演练记录" : `线上版本 ${latest.revision}`}</small><strong>{latest.status === "succeeded" ? "产品已经真实上线" : latest.status === "simulated" ? "没有创建真实云资源" : latest.status === "failed" ? "这次发布没有完成" : "正在发布产品"}</strong></div><StatusPill status={latest.status} /></div>{latest.deployment_url ? <a className="deployment-live-url" href={latest.deployment_url} target="_blank" rel="noreferrer"><Globe2 size={15} />{latest.deployment_url}<ArrowRight size={14} /></a> : <p className="deployment-no-url">{latest.status === "simulated" ? "模拟记录不会生成或展示线上地址。" : "发布完成并通过 HTTPS 检查后，地址会出现在这里。"}</p>}{["queued", "running"].includes(latest.status) && <button className="ghost-button wide" type="button" onClick={() => void load()}><RefreshCw size={15} />刷新发布状态</button>}{latest.status === "failed" && <div className="deployment-rollback"><RotateCcw size={15} />上一线上版本没有被覆盖，可以恢复。</div>}</div>}

            <footer className="deployment-step-footer">
              <button className="ghost-button" type="button" onClick={() => setSelectedStepId(STEPS[Math.max(0, STEPS.findIndex((step) => step.id === selectedStep.id) - 1)].id)} disabled={selectedStep.id === STEPS[0].id}>上一步</button>
              {completed.has(selectedStep.id) ? <button className="deployment-completed-button" type="button" onClick={() => { const index = STEPS.findIndex((step) => step.id === selectedStep.id); const next = STEPS[index + 1]; if (next) setSelectedStepId(next.id); else onNavigate("m2c"); }}><Check size={15} />已完成，继续<ArrowRight size={15} /></button> : <button className="primary-button" type="button" onClick={markCurrentComplete}>{selectedStep.owner === "AI 自动处理" ? "确认检查结果" : "这一步已完成"}<ArrowRight size={15} /></button>}
            </footer>
          </article>
        </div>
        {(deploymentDisabled || (capabilities && !realDeploymentAvailable)) && <div className="deployment-bottom-truth"><ShieldAlert size={16} /><p><strong>平台真实状态：</strong>当前发布适配器未启用，本页提供可交互的上线流程，但不会收集云密钥、创建收费资源或伪造线上地址。</p></div>}
      </div>
    </section>
  );
}
