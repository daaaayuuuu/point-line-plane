"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight, ArrowUp, Check, CheckCircle2, 
  CloudUpload, Eye, EyeOff, Globe2, History, KeyRound, LockKeyhole, Mic,
  Plus, RefreshCw, RotateCcw, Server, ShieldAlert, ShieldCheck, Square, SquarePen, TerminalSquare,
  UserRound,
} from "lucide-react";
import { CODEX_EFFORTS, CODEX_MODEL_IDS, CODEX_REASONING_EFFORT_IDS } from "@/lib/codex-models";
import { DEPLOYMENT_SKILL_STEPS as SKILL_STEPS, deploymentGuideView, usableDeploymentAuthorization, deploymentNavigationProgress } from "@/lib/deployment-guide-state";
import { api, isAppError } from "@/lib/api/client";
import type { CloudCredential, Deployment, DeploymentAuthorization, PlatformCapabilities, ProductionReadiness } from "@/lib/api/types";
import { useCodexFastMode } from "@/lib/use-codex-fast-mode";
import { CodexModelSettings } from "../CodexModelSettings";
import type { StageProps } from "../StagePanels";
import { DatabaseSetupGuide } from "./DatabaseSetupGuide";
import { StatusPill } from "../StageUi";
import { formatDate } from "../data";

// Official veFaaS application deployment policies; these are service-level grants.
const DEPLOYMENT_POLICIES = [
  { name: "VeFaaSFullAccess", purpose: "管理函数服务，上传并发布产品的前端和后端。" },
  { name: "APIGFullAccess", purpose: "管理 API 网关，为产品配置公网访问入口和路由。" },
  { name: "STSAssumeRoleAccess", purpose: "允许部署流程使用已获授权的服务角色。" },
];

function DeploymentPolicyChecklist() {
  return <div className="deployment-policy-checklist">
    <p>选择<strong>直接添加权限 → 添加权限策略</strong>，策略类型和所属服务保持“全部”。在“搜索策略名或备注”中逐个搜索下列名称，勾选对应行左侧的复选框；清空搜索后，再添加下一项。</p>
    <div className="deployment-policy-list" aria-label="需要添加的三项部署策略">
      {DEPLOYMENT_POLICIES.map((policy) => <div key={policy.name}><code>{policy.name}</code><p>{policy.purpose}</p></div>)}
    </div>
    <p>新建用户时，核对右侧<strong>已选 3 项</strong>，名称与上方一致，再点击<strong>下一步</strong>。已有用户只补缺少的策略。</p>
    <p className="deployment-policy-scope">这是火山引擎官方应用部署使用的服务级策略，请授予部署专用用户。不要勾选全选、AdministratorAccess、IAMFullAccess 或费用管理权限；若需限制到指定项目，可由管理员配置自定义策略。</p>
    <a className="deployment-help-link" href="https://www.volcengine.com/docs/6662/1323137" target="_blank" rel="noreferrer">核对火山引擎官方部署策略<ArrowRight size={14} /></a>
  </div>;
}

type RouteKey = "new_account" | "needs_services" | "ready_account";
type DeploymentStep = { id: string; title: string; summary: string; productActions: string[]; outcome: string };
type GuideMessage = {
  id: string;
  role: "assistant" | "user";
  body: string;
  agentAction?: string;
};
type DeploymentConversation = {
  id: string;
  title: string;
  updatedAt: string;
  route: RouteKey | null;
  selectedStepId: string;
  completedStepIds: string[];
  completedDeploymentId?: string | null;
  messages: GuideMessage[];
};

function compactRepeatedPlatformChecks(messages: GuideMessage[]): GuideMessage[] {
  const compacted: GuideMessage[] = [];
  for (let index = 0; index < messages.length; index += 1) {
    const current = messages[index];
    const next = messages[index + 1];
    const isPlatformCheckPair = current.role === "user"
      && current.body.trim() === "重新检测平台能力"
      && next?.role === "assistant";
    if (!isPlatformCheckPair) {
      compacted.push(current);
      continue;
    }
    const previousUser = compacted.at(-2);
    const previousAssistant = compacted.at(-1);
    if (
      previousUser?.role === "user"
      && previousUser.body.trim() === current.body.trim()
      && previousAssistant?.role === "assistant"
      && previousAssistant.body.trim() === next.body.trim()
    ) {
      compacted.splice(-2, 2);
    }
    compacted.push(current, next);
    index += 1;
  }
  return compacted;
}

type VoiceRecognitionResult = {
  readonly 0?: { readonly transcript: string };
};

type VoiceRecognitionEvent = {
  readonly resultIndex: number;
  readonly results: ArrayLike<VoiceRecognitionResult>;
};

type VoiceRecognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: VoiceRecognitionEvent) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type VoiceRecognitionConstructor = new () => VoiceRecognition;

const SUPPORTED_UPLOAD_ACCEPT = [
  ".txt", ".md", ".markdown", ".pdf", ".sql", ".csv", ".tsv", ".json", ".jsonl",
  ".yaml", ".yml", ".xml", ".html", ".htm", ".css", ".scss", ".less", ".js", ".jsx",
  ".mjs", ".ts", ".tsx", ".py", ".java", ".c", ".h", ".cpp", ".hpp", ".cs", ".go",
  ".rs", ".rb", ".php", ".sh", ".bash", ".zsh", ".toml", ".ini", ".cfg", ".conf",
  ".properties", ".log", ".rtf", ".ipynb", ".docx", ".xlsx", ".pptx", ".zip", ".tar",
  ".tar.gz", ".tgz", ".gz",
].join(",");



const STEPS: DeploymentStep[] = [
  { id: "account", title: "先登录放置产品的网站", summary: "火山引擎是让产品在网上持续运行的平台。这里要登录的是火山引擎账号，和点线面账号不同。", productActions: ["点击下方按钮打开火山引擎，选择登录；第一次使用就选择注册", "按页面提示完成登录，暂时不用购买任何服务"], outcome: "能进入火山引擎控制台，右上角显示你的账号" },
  { id: "identity", title: "确认账号已完成身份认证", summary: "火山引擎需要确认账号的使用者身份。请在它的官网完成，身份证等资料不用发给我。", productActions: ["打开控制台，点击右上角账号 → 账号管理 → 实名认证", "按实际使用主体选择个人或企业，跟随页面提交资料；如果已认证，不用重复操作"], outcome: "实名认证页面显示认证通过；审核中就等通过后再继续" },
  { id: "access", title: "连接并验证云账号", summary: "连接本次上线使用的账号，检查身份和可用服务。", productActions: ["按下方指引创建部署专用用户", "把授权信息填入安全表单，不要发到聊天里"], outcome: "页面显示账号已连接并验证" },
  { id: "operation_review", title: "确认本次操作权限", summary: "核对本次允许点线面执行的操作。", productActions: [], outcome: "本次操作已确认，继续准备线上版本" },
  { id: "permissions", title: "检查发布需要哪些权限", summary: "不需要你判断开通了哪些服务。我会先检查，列出本次真正缺少的操作权限。", productActions: ["尚未连接账号时，先通过安全表单连接", "连接后检查现有服务；需要你授权的地方会单独说明"], outcome: "得到所需权限清单；不会默认开放所有服务的全部权限" },
  { id: "mvp", title: "先试用并确认产品", summary: "先在预览中走通核心流程，再准备公开上线。", productActions: ["回到上方“生成预览”，打开当前产品", "实际试用核心功能，并在预览页完成验收确认"], outcome: "预览页记录了你确认通过的版本" },
  { id: "inspect", title: "检查现有产品和上线准备", summary: "我会读取已验收的产品版本、账号连接情况和现有发布记录，再告诉你缺什么。", productActions: ["点击下方按钮开始检查", "补充谁会使用、是否保存数据、预算和已有网址；不清楚的可以说不确定"], outcome: "一份基于实际检查的准备清单，未检查项会标为待确认" },
  { id: "online_code", title: "准备可以在线使用的版本", summary: "检查登录、用户之间的数据隔离、文件保存和故障恢复。未通过的项目需要先处理。", productActions: ["告诉我产品面向谁、数据需要保存多久、每月预算多少", "点击下方按钮查看哪些已验证、哪些仍需准备"], outcome: "得到准备结果和待处理项，通过检查后才能继续发布" },
  { id: "tools", title: "检查发布工具是否可用", summary: "发布工具由点线面维护，你不需要安装软件或输入命令。", productActions: ["点击下方按钮检查", "如果平台尚未就绪，进度会保留，恢复后再继续"], outcome: "能实际连接发布服务" },
  { id: "gateway", title: "准备让别人访问产品的入口", summary: "这个入口在火山引擎里叫“API 网关”。先检查已有入口；只有确实缺少时才引导创建。", productActions: ["先检查是否有能复用的入口", "若需要新建，先看清费用，再由你在官网确认"], outcome: "有可用的访问入口，并已明确费用范围" },
  { id: "environment", title: "检查产品运行需要的配置", summary: "检查模型连接、登录和数据保存配置是否齐全。密码只进入受保护的配置区。", productActions: ["确认需要接入的服务和登录方式", "缺少密码或授权时，只使用安全表单"], outcome: "配置检查通过，敏感信息不会出现在网页代码中" },
  { id: "backend", title: "确认本次发布内容", summary: "先核对发布位置、复用或新增的服务、费用与影响，再决定是否公开发布。", productActions: ["阅读下方方案与费用", "确认后点击正式发布；不确定时可以继续提问"], outcome: "创建一条真实发布任务，随后检查运行结果" },
  { id: "reserved", title: "确认是否需要持续运行", summary: "持续运行可能产生固定费用，也不能代替可靠的数据存储和备份。", productActions: ["结合使用量核对是否需要常驻运行", "先确认费用，才能调整配置"], outcome: "按实际需要选择，不默认购买" },
  { id: "frontend", title: "发布用户打开的网页", summary: "根据产品实际结构发布网页，并检查它能否连接所需服务。", productActions: ["等待本次发布结果", "遇到失败先定位原因，避免重复创建收费服务"], outcome: "得到待验收的网址" },
  { id: "address", title: "打开网址试用", summary: "发布成功后还要检查实际功能。能打开首页，并不代表所有功能都通过了。", productActions: ["打开下方网址，登录并走一遍核心流程", "在手机上试用，并检查刷新、换设备后数据是否还在"], outcome: "逐项记录已通过、未通过和待确认的结果" },
  { id: "auth", title: "检查每个人只能看到自己的数据", summary: "验证未登录、错误登录以及不同用户之间的访问限制。", productActions: ["确认产品采用的登录方式", "按检查结果修复数据越权问题后再发布"], outcome: "登录和用户数据隔离有实际验证证据" },
  { id: "persistence", title: "检查数据能否保存和找回", summary: "临时运行目录不能可靠保存数据。需要持久存储、备份，并实际验证恢复。", productActions: ["确认最多能接受丢失多长时间内的数据", "上线前核对备份和恢复验证结果"], outcome: "数据保存与恢复有明确方案和验证结果" },
  { id: "storage", title: "检查图片和附件能否长期读取", summary: "文件需要独立保存，产品重启或用户换设备后仍应能读取。", productActions: ["确认文件保留时间和删除规则", "查看上传、读取和跨设备测试结果"], outcome: "文件不会只留在临时运行环境中" },
  { id: "monitor", title: "检查出问题时能否发现", summary: "确认错误可定位、通知能送达，并保留恢复上一版本的方法。", productActions: ["确认故障通知送达的位置", "核对一次实际通知和恢复验证结果"], outcome: "明确出了问题到哪里看、如何恢复" },
  { id: "acceptance", title: "领取网址和使用说明", summary: "汇总访问方式、验收结果、费用、数据保存和恢复方法。尚未验证的项目会明确列出。", productActions: ["核对电脑和手机的试用结果", "保存网址、登录说明、费用关闭入口和故障处理方法"], outcome: "可分享的网址，以及有证据支持的上线结果" },
];

const INITIAL_MESSAGES: GuideMessage[] = [
  { id: "welcome", role: "assistant", body: "我会带你把产品放到网上，让别人通过网址使用。先检查准备情况，再说明方案和费用；需要你操作时，会告诉你入口、点击位置和完成标志。" },
  { id: "route-question", role: "assistant", body: "无论之前是否登录或连接过账号，本次上线都请先重新连接火山引擎账号。" },
];

const DEPLOYMENT_STARTERS = [
  { label: "检查你的产品是否已经准备好上线", icon: UserRound },
  { label: "能自动完成的上线工作都交给我", icon: TerminalSquare },
  { label: "需要你操作时，我会一步一步带你完成", icon: KeyRound },
  { label: "上线后，你会得到一个可以分享的网址", icon: CloudUpload },
  { label: "朋友、同事或客户打开网址就能使用", icon: ShieldCheck },
] as const;

function conversationId() {
  return `deployment-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function emptyConversation(): DeploymentConversation {
  return {
    id: conversationId(),
    title: "新的上线对话",
    updatedAt: new Date().toISOString(),
    route: null,
    selectedStepId: "account",
    completedStepIds: [],
    messages: INITIAL_MESSAGES,
  };
}

function CodexMark() {
  return (
    <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor" fillRule="evenodd" aria-hidden="true">
      <path d="M9.205 8.658v-2.26c0-.19.072-.333.238-.428l4.543-2.616c.619-.357 1.356-.523 2.117-.523 2.854 0 4.662 2.212 4.662 4.566 0 .167 0 .357-.024.547l-4.71-2.759a.797.797 0 0 0-.856 0l-5.97 3.473Zm10.609 8.8V12.06c0-.333-.143-.57-.429-.737l-5.97-3.473 1.95-1.118a.433.433 0 0 1 .476 0l4.543 2.617c1.309.76 2.189 2.378 2.189 3.948 0 1.808-1.07 3.473-2.76 4.163ZM7.802 12.703l-1.95-1.142c-.167-.095-.239-.238-.239-.428V5.899c0-2.545 1.95-4.472 4.591-4.472 1 0 1.927.333 2.712.928L8.23 5.067c-.285.166-.428.404-.428.737v6.898ZM12 15.128l-2.795-1.57v-3.33L12 8.658l2.795 1.57v3.33L12 15.128Zm1.796 7.23c-1 0-1.927-.332-2.712-.927l4.686-2.712c.285-.166.428-.404.428-.737v-6.898l1.974 1.142c.167.095.238.238.238.428v5.233c0 2.545-1.974 4.472-4.614 4.472Zm-5.637-5.303-4.544-2.617c-1.308-.761-2.188-2.378-2.188-3.948A4.482 4.482 0 0 1 4.21 6.327v5.423c0 .333.143.571.428.738l5.947 3.449-1.95 1.118a.432.432 0 0 1-.476 0Zm-.262 3.9c-2.688 0-4.662-2.021-4.662-4.519 0-.19.024-.38.047-.57l4.686 2.71c.286.167.571.167.856 0l5.97-3.448v2.26c0 .19-.07.333-.237.428l-4.543 2.616c-.619.357-1.356.523-2.117.523Zm5.899 2.83a5.947 5.947 0 0 0 5.827-4.756C22.287 18.339 24 15.84 24 13.296c0-1.665-.713-3.282-1.998-4.448.119-.5.19-.999.19-1.498 0-3.401-2.759-5.947-5.946-5.947-.642 0-1.26.095-1.88.31A5.962 5.962 0 0 0 10.205 0a5.947 5.947 0 0 0-5.827 4.757C1.713 5.447 0 7.945 0 10.49c0 1.666.713 3.283 1.998 4.448-.119.5-.19 1-.19 1.499 0 3.401 2.759 5.946 5.946 5.946.642 0 1.26-.095 1.88-.309a5.96 5.96 0 0 0 4.162 1.713Z" />
    </svg>
  );
}

function routeForStep(stepId: string): RouteKey {
  if (["account", "identity", "access"].includes(stepId)) return "new_account";
  if (["permissions", "gateway"].includes(stepId)) return "needs_services";
  return "ready_account";
}

export function M2BDeployment({ project, onProjectChange, onRefresh, onError, onNotice }: StageProps) {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [credential, setCredential] = useState<CloudCredential | null>(null);
  const [reconnecting, setReconnecting] = useState(true);
  const [authorization, setAuthorization] = useState<DeploymentAuthorization | null>(null);
  const [productionReadiness, setProductionReadiness] = useState<ProductionReadiness | null>(null);
  const [databaseUrl, setDatabaseUrl] = useState("");
  const [additionalEnvironment, setAdditionalEnvironment] = useState<Record<string, string>>({});
  const [runtimeLoaded, setRuntimeLoaded] = useState(false);
  const [capabilities, setCapabilities] = useState<PlatformCapabilities | null>(null);
  const [accessKey, setAccessKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [showSecrets, setShowSecrets] = useState(false);
  const [activeCredentialField, setActiveCredentialField] = useState<"access" | "secret" | null>(null);
  const [checkingPlatform, setCheckingPlatform] = useState(false);
  const [platformCheckResult, setPlatformCheckResult] = useState<"idle" | "unavailable" | "permission_required" | "activation_required">("idle");
  const [authorizationClock, setAuthorizationClock] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [route, setRoute] = useState<RouteKey | null>(null);
  const [selectedStepId, setWorkflowStepId] = useState("account");
  const [browsingStepId, setBrowsingStepId] = useState<string | null>(null);
  const [conversationExpanded, setConversationExpanded] = useState(false);
  function setSelectedStepId(stepId: string) {
    setBrowsingStepId(null);
    setWorkflowStepId(stepId);
  }
  const [completedStepIds, setCompletedStepIds] = useState<string[]>([]);
  const [completedDeploymentId, setCompletedDeploymentId] = useState<string | null>(null);
  const [messages, setMessages] = useState<GuideMessage[]>(INITIAL_MESSAGES);
  const [messageDraft, setMessageDraft] = useState("");
  const [guideHydrated, setGuideHydrated] = useState(false);
  const [activeConversationId, setActiveConversationId] = useState("");
  const [conversationTitle, setConversationTitle] = useState("新的上线对话");
  const [conversationHistory, setConversationHistory] = useState<DeploymentConversation[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [replying, setReplying] = useState(false);
  const [thinkingSeconds, setThinkingSeconds] = useState(0);
  const [fastMode, setFastMode] = useCodexFastMode();
  const [model, setModel] = useState("5.6 Sol");
  const [reasoningEffort, setReasoningEffort] = useState<(typeof CODEX_EFFORTS)[number]>("中");
  const [openComposerMenu, setOpenComposerMenu] = useState<"models" | null>(null);
  const [listening, setListening] = useState(false);
  const [gatewayRequired, setGatewayRequired] = useState(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const historyRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLFormElement | null>(null);
  const messageDraftRef = useRef<HTMLTextAreaElement | null>(null);
  useEffect(() => {
    function resizeDraft() {
      const input = messageDraftRef.current;
      if (!input) return;
      input.style.height = "auto";
      input.style.height = `${Math.min(input.scrollHeight, 168)}px`;
    }
    resizeDraft();
    window.addEventListener("resize", resizeDraft);
    return () => window.removeEventListener("resize", resizeDraft);
  }, [messageDraft]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const voiceRecognitionRef = useRef<VoiceRecognition | null>(null);
  const deploymentAbortRef = useRef<AbortController | null>(null);
  const suppressPersistRef = useRef(false);
  const hydratedProjectRef = useRef("");

  const load = useCallback(async () => {
    try {
      const [deploymentResult, runtime, credentialResult, authorizationResult, readinessResult] = await Promise.all([
        api.deployments(project.id), api.capabilities(), api.cloudCredentials(project.id), api.deploymentAuthorizations(project.id), api.productionReadiness(project.id),
      ]);
      const activeCredential = credentialResult.items.find((item) => !["revoked", "expired", "invalid"].includes(item.status)) ?? null;
      setDeployments(deploymentResult.items);
      setCapabilities(runtime);
      setCredential(activeCredential);
      setAuthorization(authorizationResult.items.find((item) => ["pending", "confirmed"].includes(item.status) && Date.parse(item.expires_at) > Date.now()) ?? null);
      setProductionReadiness(readinessResult);
      setRuntimeLoaded(true);
    } catch (value) { if (!(isAppError(value) && value.status === 404)) onError(value); }
  }, [onError, project.id]);

  useEffect(() => {
    const timer = window.setInterval(() => setAuthorizationClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!deployments.some((item) => ["queued", "running"].includes(item.status))) return;
    const timer = window.setInterval(() => { void load(); }, 5000);
    return () => window.clearInterval(timer);
  }, [deployments, load]);
  useEffect(() => { const timer = window.setTimeout(() => { void load(); }, 0); return () => window.clearTimeout(timer); }, [load]);
  useEffect(() => {
    const key = `deployment-conversations:${project.id}`;
    hydratedProjectRef.current = "";
    const timer = window.setTimeout(() => {
      try {
        const entryKey = `deployment-fresh-entry:${project.id}`;
        const policyKey = `deployment-entry-policy:${project.id}`;
        const freshEntry = window.sessionStorage.getItem(entryKey) === "new" || window.localStorage.getItem(policyKey) !== "2";
        const raw = window.localStorage.getItem(key);
        if (raw) {
          const saved = JSON.parse(raw) as { activeId?: string; items?: DeploymentConversation[] };
          const items = Array.isArray(saved.items)
            ? saved.items
              .filter((item) => item && typeof item.id === "string")
              .slice(0, 20)
              .map((item) => ({ ...item, messages: compactRepeatedPlatformChecks(item.messages ?? []).map((message) => INITIAL_MESSAGES.find((initial) => initial.id === message.id) ?? (message.role === "assistant" && message.body === "这个产品已经保存了火山引擎的连接信息，不用重新注册或填写。点击下方按钮继续检查。" ? { ...message, body: "本次上线请先重新连接火山引擎账号。点击下方按钮，重新填写授权信息并验证连接。" } : message)) }))
            : [];
          if (items.length) {
            if (freshEntry) items.unshift(emptyConversation());
            const active = freshEntry ? items[0] : items.find((item) => item.id === saved.activeId) ?? items[0];
            window.sessionStorage.removeItem(entryKey);
            window.localStorage.setItem(policyKey, "2");
            window.localStorage.setItem(key, JSON.stringify({ activeId: active.id, items }));
            suppressPersistRef.current = true;
            setConversationHistory(items);
            setActiveConversationId(active.id);
            setConversationTitle(active.title || "上线部署对话");
            setRoute(active.route ?? null);
            setSelectedStepId(STEPS.some((step) => step.id === active.selectedStepId) ? active.selectedStepId : "account");
            setCompletedDeploymentId(active.completedDeploymentId ?? null);
            setCompletedStepIds((active.completedStepIds ?? []).filter((id) => STEPS.some((step) => step.id === id)));
            setMessages(Array.isArray(active.messages) && active.messages.length ? active.messages.slice(-24) : INITIAL_MESSAGES);
            hydratedProjectRef.current = project.id;
            setGuideHydrated(true);
            return;
          }
        }
      } catch { window.localStorage.removeItem(key); }
      const initial = emptyConversation();
      window.sessionStorage.removeItem(`deployment-fresh-entry:${project.id}`);
      window.localStorage.setItem(`deployment-entry-policy:${project.id}`, "2");
      window.localStorage.setItem(key, JSON.stringify({ activeId: initial.id, items: [initial] }));
      suppressPersistRef.current = true;
      setConversationHistory([initial]);
      setActiveConversationId(initial.id);
      setConversationTitle(initial.title);
      setRoute(null);
      setSelectedStepId("account");
      setCompletedStepIds([]);
      setMessages(INITIAL_MESSAGES);
      hydratedProjectRef.current = project.id;
      setGuideHydrated(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [project.id]);
  useEffect(() => {
    if (!guideHydrated || hydratedProjectRef.current !== project.id || !activeConversationId) return;
    if (suppressPersistRef.current) { suppressPersistRef.current = false; return; }
    const snapshot: DeploymentConversation = {
      id: activeConversationId,
      title: conversationTitle,
      updatedAt: new Date().toISOString(),
      route,
      selectedStepId,
      completedStepIds,
      completedDeploymentId,
      messages: messages.slice(-24),
    };
    setConversationHistory((current) => {
      const next = [snapshot, ...current.filter((item) => item.id !== activeConversationId)].slice(0, 20);
      window.localStorage.setItem(`deployment-conversations:${project.id}`, JSON.stringify({ activeId: activeConversationId, items: next }));
      return next;
    });
  }, [activeConversationId, completedStepIds, completedDeploymentId, conversationTitle, guideHydrated, messages, project.id, route, selectedStepId]);
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const action = !replying && chatEndRef.current?.parentElement?.querySelector(".deployment-connect-guide, .deployment-authorization, .deployment-live-result, .deployment-route-question");
      if (action) action.scrollIntoView({ block: "start" });
      else chatEndRef.current?.scrollIntoView({ block: "nearest" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [messages, replying, route, selectedStepId, browsingStepId]);
  useEffect(() => {
    if (!replying) return;
    const timer = window.setInterval(() => setThinkingSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [replying]);
  useEffect(() => {
    function closeHistory(event: MouseEvent) {
      if (historyRef.current && !historyRef.current.contains(event.target as Node)) setHistoryOpen(false);
      if (composerRef.current && !composerRef.current.contains(event.target as Node)) setOpenComposerMenu(null);
    }
    function closeWithEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setHistoryOpen(false);
        setOpenComposerMenu(null);
      }
    }
    document.addEventListener("mousedown", closeHistory);
    document.addEventListener("keydown", closeWithEscape);
    return () => { document.removeEventListener("mousedown", closeHistory); document.removeEventListener("keydown", closeWithEscape); };
  }, []);
  useEffect(() => () => {
    deploymentAbortRef.current?.abort();
    voiceRecognitionRef.current?.abort();
  }, []);

  const latest = deployments[0];
  const handoffComplete = Boolean(route && messages.some((item) => item.role === "user") && latest?.status === "succeeded" && completedDeploymentId === latest.id);
  const realDeploymentAvailable = Boolean(capabilities?.deployment_enabled && capabilities.deployment_mode === "external");
  const providerLabel = capabilities?.deployment_provider === "volcano_engine" ? "火山引擎 veFaaS" : capabilities?.deployment_provider ?? "发布服务读取中";
  const regionLabel = capabilities?.deployment_region === "cn-beijing" ? "华北 2（北京）" : capabilities?.deployment_region ?? "位置读取中";
  const effectiveSelectedStepId = browsingStepId ?? selectedStepId;
  const selectedStep = STEPS.find((step) => step.id === effectiveSelectedStepId) ?? STEPS[0];
  const hasStartedConversation = messages.some((item) => item.role === "user");
  const storedSkillStepIndex = Math.max(0, SKILL_STEPS.findIndex((step) => (step.stepIds as readonly string[]).includes(selectedStep.id)));
  const selectedSkillStepIndex = !browsingStepId && latest?.status === "succeeded" && storedSkillStepIndex === 4 ? 5 : storedSkillStepIndex;
  const workflowSkillStepIndex = Math.max(0, SKILL_STEPS.findIndex((step) => (step.stepIds as readonly string[]).includes(selectedStepId)));
  const navigationProgress = deploymentNavigationProgress(Boolean(route && hasStartedConversation), workflowSkillStepIndex, latest?.status === "succeeded", handoffComplete);
  const completedThroughIndex = navigationProgress.completedThrough;
  const estimatedCost = authorization?.estimated_cost ?? {};
  const resourcePlan = (estimatedCost.resource_plan && typeof estimatedCost.resource_plan === "object")
    ? estimatedCost.resource_plan as Record<string, unknown>
    : {};
  const gatewayLabel = typeof resourcePlan.gateway === "string"
    ? `复用 ${resourcePlan.gateway}`
    : resourcePlan.gateway_action === "reuse_bound_gateway"
      ? "复用应用现有网关"
      : "待检测";
  const authorizationUsable = usableDeploymentAuthorization(authorization, authorizationClock);
  const costLabel = estimatedCost.pricing_configured && typeof estimatedCost.amount_minor === "number"
    ? `${estimatedCost.currency === "CNY" ? "¥" : String(estimatedCost.currency ?? "")} ${(Number(estimatedCost.amount_minor) / 100).toFixed(2)}` : "待确认，发布后可能按使用量计费";
  const deploymentPrompt = `帮我上线 ${project.name}`;
  const guideView = deploymentGuideView(route, selectedStep.id, Boolean(credential), Boolean(latest));
  const showResult = guideView.result && !(["address", "acceptance"].includes(selectedStep.id) && latest?.status !== "succeeded") && !(selectedStep.id === "backend" && authorizationUsable && latest?.status !== "succeeded");
  const showGateway = guideView.gateway;

  function fillComposer(prompt: string) {
    setMessageDraft(prompt);
    setOpenComposerMenu(null);
    window.requestAnimationFrame(() => {
      composerRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
      window.setTimeout(() => {
        messageDraftRef.current?.focus();
        messageDraftRef.current?.setSelectionRange(prompt.length, prompt.length);
      }, 240);
    });
  }

  function appendMessages(...items: Array<Omit<GuideMessage, "id">>) {
    setMessages((current) => [...current, ...items.map((item, index) => ({ ...item, id: `${Date.now()}-${index}` }))].slice(-24));
  }
  function currentConversationSnapshot(): DeploymentConversation {
    return {
      id: activeConversationId,
      title: conversationTitle,
      updatedAt: new Date().toISOString(),
      route,
      selectedStepId,
      completedStepIds,
      completedDeploymentId,
      messages: messages.slice(-24),
    };
  }
  function saveConversationList(items: DeploymentConversation[], nextActiveId: string) {
    window.localStorage.setItem(`deployment-conversations:${project.id}`, JSON.stringify({ activeId: nextActiveId, items: items.slice(0, 20) }));
  }
  function stopReplying(addMessage = false) {
    deploymentAbortRef.current?.abort();
    deploymentAbortRef.current = null;
    setReplying(false);
    setThinkingSeconds(0);
    if (addMessage) appendMessages({ role: "assistant", body: "已停止本次分析。你可以补充上线情况后重新发送。" });
  }
  function createConversation() {
    if (!activeConversationId) return;
    stopReplying();
    const current = currentConversationSnapshot();
    const created = emptyConversation();
    const next = [created, current, ...conversationHistory.filter((item) => item.id !== current.id)].slice(0, 20);
    suppressPersistRef.current = true;
    setConversationHistory(next);
    setActiveConversationId(created.id);
    setConversationTitle(created.title);
    setRoute(null);
    setSelectedStepId("account");
    setCompletedStepIds([]);
    setCompletedDeploymentId(null);
    setMessages(INITIAL_MESSAGES);
    setMessageDraft("");
    setHistoryOpen(false);
    setGatewayRequired(false);
    setPlatformCheckResult("idle");
    saveConversationList(next, created.id);
  }
  function activateConversation(nextConversationId: string) {
    if (nextConversationId === activeConversationId) { setHistoryOpen(false); return; }
    const current = currentConversationSnapshot();
    const nextHistory = [current, ...conversationHistory.filter((item) => item.id !== current.id)];
    const target = nextHistory.find((item) => item.id === nextConversationId);
    if (!target) return;
    stopReplying();
    suppressPersistRef.current = true;
    setConversationHistory(nextHistory);
    setActiveConversationId(target.id);
    setConversationTitle(target.title);
    setRoute(target.route);
    setSelectedStepId(STEPS.some((step) => step.id === target.selectedStepId) ? target.selectedStepId : "account");
    setCompletedStepIds(target.completedStepIds);
    setCompletedDeploymentId(target.completedDeploymentId ?? null);
    setMessages(target.messages);
    setMessageDraft("");
    setHistoryOpen(false);
    setGatewayRequired(false);
    setPlatformCheckResult("idle");
    saveConversationList(nextHistory, target.id);
  }
  function reconnectAccount() {
    setReconnecting(true);
    setAccessKey("");
    setSecretKey("");
    setShowSecrets(false);
    setActiveCredentialField(null);
    setAuthorization(null);
    setGatewayRequired(false);
    setPlatformCheckResult("idle");
    setCompletedStepIds([]);
    setRoute("ready_account");
    setSelectedStepId("access");
  }
  function resetGuide() {
    stopReplying();
    setRoute(null);
    setSelectedStepId("account");
    setGatewayRequired(false);
    appendMessages({ role: "assistant", body: "我们回到准备步骤，请重新连接火山引擎账号后继续。" });
  }
  async function sendMessage(overrideContent?: string) {
    const content = (overrideContent ?? messageDraft).trim(); if (!content || replying || busy) return;
    setConversationExpanded(true);
    if (!route && /^(帮我上线|开始上线|上线)/.test(content)) {
      setMessageDraft("");
      setConversationTitle(content.slice(0, 22));
      appendMessages({ role: "user", body: content }, { role: "assistant", body: "本次上线请先重新连接火山引擎账号。点击下方按钮，重新填写授权信息并验证连接。" });
      return;
    }
    setMessageDraft("");
    setConversationTitle((current) => current === "新的上线对话" ? content.slice(0, 22) : current);
    appendMessages({ role: "user", body: content });
    setThinkingSeconds(0);
    setReplying(true);
    const controller = new AbortController();
    deploymentAbortRef.current = controller;
    try {
      const result = await api.deploymentAgentMessage(
        project.id,
        activeConversationId,
        content,
        controller.signal,
        {
          model: CODEX_MODEL_IDS[model],
          reasoningEffort: CODEX_REASONING_EFFORT_IDS[reasoningEffort],
          serviceTier: fastMode ? "fast" : "default",
        },
      );
      if (controller.signal.aborted || deploymentAbortRef.current !== controller) return;
      appendMessages({ role: "assistant", body: result.reply, agentAction: result.action });
      if (result.project.stage !== project.stage) onProjectChange(result.project);
      if (result.selected_step_id && STEPS.some((step) => step.id === result.selected_step_id)) {
        setSelectedStepId(reconnecting ? "access" : result.authorization?.status === "pending" ? "permissions" : result.selected_step_id);
        setRoute((current) => current ?? routeForStep(result.selected_step_id as string));
      }
      if (result.authorization) setAuthorization(result.authorization);
      if (result.deployment) {
        setDeployments((current) => [result.deployment!, ...current.filter((item) => item.id !== result.deployment!.id)]);
      }
      await load();
    } catch (value) {
      if (controller.signal.aborted || deploymentAbortRef.current !== controller) return;
      if (isAppError(value) && ["PRODUCTION_DATABASE_REQUIRED", "PRODUCTION_PACKAGE_REQUIRED", "PREVIEW_ACCEPTANCE_REQUIRED", "DEPLOYMENT_CONFIGURATION_CHANGED", "DEPLOYMENT_VERSION_CHANGED"].includes(value.code)) {
        setRoute("ready_account"); setSelectedStepId("inspect");
        setAuthorization(null);
        setProductionReadiness(await api.productionReadiness(project.id));
        onNotice(value.userMessage); return;
      }
      if (isAppError(value) && value.code === "CLOUD_API_GATEWAY_REQUIRED") {
        setAuthorization(null);
        setGatewayRequired(true);
        setRoute("needs_services");
        setSelectedStepId("gateway");
        appendMessages({ role: "assistant", body: "刚刚检查：本次发布还缺少让别人访问产品的入口。请按下方指引操作，完成后回来重新检查。" });
        return;
      }
      if (!(value instanceof DOMException && value.name === "AbortError")) {
        setMessageDraft(content);
        onError(value);
      }
    } finally {
      if (deploymentAbortRef.current === controller) {
        deploymentAbortRef.current = null;
        setReplying(false);
        setThinkingSeconds(0);
      }
    }
  }
  async function recheckPlatformCapability() {
    if (checkingPlatform || replying || busy) return;
    setCheckingPlatform(true);
    setPlatformCheckResult("idle");
    try {
      const runtime = await api.capabilities();
      setCapabilities(runtime);
      const available = Boolean(runtime.deployment_enabled && runtime.deployment_mode === "external");
      if (available) {
        if (credential && credential.status !== "verified") {
          const verified = await api.verifyCloudCredential(credential.id);
          setCredential(verified);
        }
        await load();
        onNotice(credential ? "检测完成，账号连接状态已更新。" : "发布服务已可用，请先安全连接账号。");
      } else {
        setPlatformCheckResult("unavailable");
        onNotice("检测完成：平台部署能力仍未开通，你无需操作。");
      }
    } catch (value) {
      if (isAppError(value) && value.code === "CLOUD_PROVIDER_PERMISSION_DENIED") {
        setPlatformCheckResult("permission_required");
      }
      onError(value);
    } finally {
      setCheckingPlatform(false);
    }
  }
  function toggleDictation() {
    setOpenComposerMenu(null);
    if (listening) {
      voiceRecognitionRef.current?.stop();
      return;
    }
    const browserWindow = window as Window & {
      SpeechRecognition?: VoiceRecognitionConstructor;
      webkitSpeechRecognition?: VoiceRecognitionConstructor;
    };
    const Recognition = browserWindow.SpeechRecognition ?? browserWindow.webkitSpeechRecognition;
    if (!Recognition) {
      onError({
        code: "VOICE_INPUT_UNAVAILABLE",
        userMessage: "当前浏览器暂不支持语音输入，请使用文字输入。",
        message: "Speech recognition is unavailable",
        retryable: false,
      });
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "zh-CN";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      let transcript = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        transcript += event.results[index]?.[0]?.transcript ?? "";
      }
      if (transcript.trim()) {
        setMessageDraft((value) => `${value}${value.trim() ? " " : ""}${transcript.trim()}`);
        requestAnimationFrame(() => messageDraftRef.current?.focus());
      }
    };
    recognition.onerror = () => {
      onError({
        code: "VOICE_INPUT_FAILED",
        userMessage: "没有识别到语音，请重试或改用文字输入。",
        message: "Speech recognition failed",
        retryable: true,
      });
    };
    recognition.onend = () => {
      voiceRecognitionRef.current = null;
      setListening(false);
    };
    voiceRecognitionRef.current = recognition;
    setListening(true);
    recognition.start();
  }
  async function uploadDeploymentFile(file: File) {
    setOpenComposerMenu(null);
    setBusy(true);
    try {
      const response = await api.uploadDeploymentAttachment(project.id, file);
      setConversationTitle((current) => current === "新的上线对话" ? file.name.slice(0, 22) : current);
      appendMessages(
        { role: "user", body: `已上传文件：${response.filename}` },
        { role: "assistant", body: response.reply },
      );
      onNotice(`已读取 ${response.filename}，文件原文不会写入部署记录。`);
    } catch (value) {
      onError(value);
    } finally {
      setBusy(false);
    }
  }

  async function connectCloud(useSaved = false) {
    setBusy(true);
    setPlatformCheckResult("idle");
    try {
      const created = useSaved && credential
        ? await api.verifyCloudCredential(credential.id)
        : await api.connectCloudCredential(project.id, accessKey.trim(), secretKey.trim());
      setReconnecting(false); setAuthorization(null);
      setCredential(created); setAccessKey(""); setSecretKey("");
      if (created.status === "verified") {
        setRoute("ready_account");
        setSelectedStepId("inspect");
        setCompletedStepIds((current) => [...new Set([...current, "account", "identity", "access"])]);
      }
      onNotice(created.status === "verified" ? "火山引擎账号已连接并通过身份校验。" : "火山引擎授权已加密保存，原文已从页面清空。");
      appendMessages({
        role: "assistant",
        body: created.status === "verified"
          ? "账号身份校验通过。接下来检查上线准备，再进入第 2 步查看方案和费用。"
          : "云账号授权已安全保存，你不用重复填写。当前点线面的部署通道还未启动；我会保留进度，通道启动后再完成真实身份校验。",
      });
    } catch (value) {
      if (isAppError(value) && value.code === "CLOUD_SERVICE_ACTIVATION_REQUIRED") setPlatformCheckResult("activation_required");
      if (isAppError(value) && value.code === "CLOUD_PROVIDER_PERMISSION_DENIED") setPlatformCheckResult("permission_required");
      onError(value);
    }
    finally { setBusy(false); }
  }
  async function quote() {
    if (busy || replying) return;
    if (!credential || credential.status !== "verified") { setSelectedStepId("access"); return; }
    setBusy(true);
    try {
      if (reconnecting) {
        const verified = await api.verifyCloudCredential(credential.id);
        setCredential(verified); setReconnecting(false);
      }
      const result = await api.quoteDeployment(project.id, credential.id, capabilities?.deployment_region);
      setAuthorization(result);
      setGatewayRequired(false);
      setSelectedStepId("permissions");
      onNotice("方案检查完成，请先查看发布位置、服务范围和费用。");
    } catch (value) {
      if (isAppError(value) && ["PRODUCTION_DATABASE_REQUIRED", "PRODUCTION_PACKAGE_REQUIRED", "PREVIEW_ACCEPTANCE_REQUIRED", "DEPLOYMENT_CONFIGURATION_CHANGED", "DEPLOYMENT_VERSION_CHANGED"].includes(value.code)) {
        setRoute("ready_account"); setSelectedStepId("inspect");
        setAuthorization(null);
        setProductionReadiness(await api.productionReadiness(project.id));
        onNotice(value.userMessage); return;
      }
      if (isAppError(value) && value.code === "CLOUD_API_GATEWAY_REQUIRED") {
        setAuthorization(null);
        setGatewayRequired(true);
        setSelectedStepId("gateway");
        onNotice("已检查：还需要产品访问入口。请按卡片指引操作。");
        return;
      }
      onError(value);
    } finally { setBusy(false); }
  }
  async function confirmAndDeploy() {
    if (!authorization || busy || replying) return;
    // Read the clock when the user confirms, so an expired authorization cannot be reused.
    if (!usableDeploymentAuthorization(authorization, Date.now())) { setAuthorization(null); onNotice("确认信息已过期，请重新检查方案和费用。"); return; }
    setBusy(true);
    try {
      const confirmed = authorization.status === "confirmed" ? authorization : await api.confirmDeployment(authorization.id);
      setAuthorization(confirmed); await api.startDeployment(project.id, confirmed.id); await load(); await onRefresh(); setSelectedStepId("backend");
      onNotice("产品已经开始发布，进度会自动保存。"); appendMessages({ role: "assistant", body: "正式发布已经开始。接下来会检查执行结果；若中途失败，会保留错误记录并说明下一步。" });
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  async function confirmOperationScope() {
    if (!authorization || busy || replying) return;
    // Read the clock when the user confirms, so an expired authorization cannot be reused.
    // eslint-disable-next-line react-hooks/purity
    if (!usableDeploymentAuthorization(authorization, Date.now())) {
      setAuthorization(null); setSelectedStepId("permissions");
      onNotice("方案已过期，请重新检查费用和操作范围。"); return;
    }
    setBusy(true);
    try {
      const confirmed = authorization.status === "confirmed" ? authorization : await api.confirmDeployment(authorization.id);
      setAuthorization(confirmed);
      setCompletedStepIds((current) => [...new Set([...current, "permissions", "operation_review"])]);
      setSelectedStepId("online_code");
      onNotice("本次操作范围已确认，接下来核对线上版本与数据配置。");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  function renderPlanReview() {
    const confirming = selectedStep.id === "operation_review";
    if (confirming) return <section className="deployment-connect-guide deployment-stage-card" aria-label="确认本次操作权限">
      <header><span><ShieldCheck size={18} /></span><div><strong>确认操作权限</strong><small>第 3 步 · 核对本次允许执行的范围</small></div></header>
      <p className="deployment-guide-intro">确认只针对当前产品和本次方案。连接账号不等于同意所有后续操作。</p>
      <div className="deployment-stage-grid"><div><h4>操作对象</h4><p>{project.name}</p><small>{providerLabel} · {regionLabel}</small></div><div><h4>允许的操作</h4><p>按确认方案准备并发布当前产品</p><small>正式发布仍需点击第 5 步的确认按钮。</small></div><div><h4>涉及的资源</h4><p>{gatewayLabel}</p><small>以第 2 步返回的服务范围为准，尚未检测的资源需先核对。</small></div><div><h4>需要另外确认</h4><p>新增购买、扩大资源范围或删除服务</p><small>查看步骤不会执行这些操作。</small></div></div>
      {latest?.status === "succeeded" && !authorizationUsable ? <p className="deployment-stage-next">当前版本已发布。再次发布前，需要重新查看方案并确认本次操作范围。</p> : authorizationUsable ? <button className="primary-button wide" type="button" disabled={busy || replying} onClick={() => void confirmOperationScope()}>确认本次范围，继续准备版本<ArrowRight size={15} /></button> : <button className="ghost-button wide" type="button" onClick={() => setSelectedStepId("permissions")}>先到第 2 步查看本次方案<ArrowRight size={15} /></button>}
    </section>;

    return <section className="deployment-connect-guide" aria-label={confirming ? "确认本次操作权限" : "查看上线方案和费用"}>
      <header><span><ShieldCheck size={18} /></span><div><strong>看懂方案费用</strong><small className="deployment-reconnect-description">{confirming ? "第 3 步 · 确认后继续准备线上版本" : "第 2 步 · 看过方案后，再确认操作权限"}</small></div></header>
      <div className="deployment-stage-grid"><div><h4>网站运行服务</h4><p>{providerLabel}</p><small>用于托管产品并运行页面所需服务。</small></div><div><h4>访问入口</h4><p>{gatewayLabel}</p><small>让其他人通过网址访问产品。</small></div><div><h4>数据与其他服务</h4><p>{productionReadiness?.storage_mode === "browser_local" ? "当前选择浏览器保存，无需云数据库" : "按产品实际依赖配置"}</p><small>需要的服务保留引导，在第 4 步完成配置。</small></div><div><h4>预计费用</h4><p>{costLabel}</p><small>运行、流量及额外服务按实际计费；准确金额以账单为准。</small></div></div>
      {!authorizationUsable ? <><p className="deployment-guide-intro">先检查可用的访问入口、发布位置和费用。检查结果出来后，再由你决定是否继续。</p><button className="primary-button" type="button" disabled={busy || replying || !realDeploymentAvailable} onClick={() => void quote()}>{busy ? "正在检查方案和费用…" : "检查方案和费用"}<ArrowRight size={15} /></button>{!realDeploymentAvailable && <p role="status">发布服务暂未就绪，请返回账号连接步骤检测。</p>}</> : <>
        <p className="deployment-stage-next">发布位置：{regionLabel} · 方案有效期：{formatDate(authorization!.expires_at)}</p>
        <p className="deployment-guide-intro">{confirming ? "本次许可仅适用于上方方案。确认后进入线上版本准备，正式发布时还会请你确认。" : "费用未返回准确金额时，以火山引擎账单为准。可以先在对话中问清楚，再继续。"}</p>
        <button className="primary-button" type="button" disabled={busy || replying} onClick={() => confirming ? void confirmOperationScope() : setSelectedStepId("operation_review")}>{busy ? "正在确认…" : confirming ? "确认本次操作，继续准备版本" : "我已了解方案，下一步确认权限"}<ArrowRight size={15} /></button>
        {confirming && <button className="ghost-button" type="button" disabled={busy || replying} onClick={() => setSelectedStepId("permissions")}>返回查看方案和费用</button>}
      </>}
    </section>;
  }

  async function connectDatabase() {
    if (busy || replying || !databaseUrl.trim()) return;
    setBusy(true);
    try {
      const result = await api.connectDeploymentDatabase(project.id, databaseUrl.trim(), additionalEnvironment);
      setProductionReadiness(result); setDatabaseUrl(""); setAdditionalEnvironment({}); setAuthorization(null);
      onNotice("数据库连接已验证并加密保存。请重新查看方案后确认发布。");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  async function selectLightweight() {
    if (busy || replying) return;
    setBusy(true);
    try {
      setProductionReadiness(await api.selectLightweightDeployment(project.id));
      setDatabaseUrl(""); setAdditionalEnvironment({}); setAuthorization(null);
      onNotice("已选择轻量版，无需云数据库。接下来查看发布方案和费用。");
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  function renderProductionPreparation() {
    const checkingResources = selectedStep.id === "inspect";
    const light = productionReadiness?.storage_mode === "browser_local";
    if (checkingResources) return <section className="deployment-connect-guide deployment-stage-card" aria-label="检查上线准备">
      <header><span><Check size={18} /></span><div><strong>检查上线准备</strong><small>第 1 步 · 确认产品和账号已齐备</small></div></header>
      <p className="deployment-guide-intro">先确认要发布哪个产品，以及是否已经试用、连接云账号。服务配置在第 4 步完成。</p>
      <div className="deployment-stage-grid">
        <div><h4>本次产品</h4><p>{project.name}</p><small>{productionReadiness?.package_ready ? `第 ${productionReadiness.code_version} 版已通过本地测试` : "发布版本还需准备"}</small></div>
        <div><h4>产品试用</h4><p>{productionReadiness?.preview_accepted ? "已确认当前预览版本" : "请先试用并确认预览版本"}</p><a href={`/?project=${project.id}&phase=build&stage=m1c`}>查看产品预览<ArrowRight size={14} /></a></div>
        <div><h4>云账号连接</h4><p>{credential?.status === "verified" ? "账号已连接" : "尚未完成账号连接"}</p><button type="button" onClick={() => setSelectedStepId("access")}>{credential ? "查看账号连接" : "连接云账号"}<ArrowRight size={14} /></button></div>
        <div><h4>上线目标</h4><p>{light ? "轻量预览 · 让别人通过网址试用" : "按当前产品所需服务发布"}</p><small>沿用第三阶段的产品范围与数据保存需求。</small></div>
      </div>
      <button className="ghost-button wide" disabled={busy || replying} onClick={() => void load()}>重新检查准备情况<RefreshCw size={15} /></button>
    </section>;

    return <section className="deployment-connect-guide" aria-label="完整产品上线准备">
      <header><span><Server size={18} /></span><div><strong>{checkingResources ? (productionReadiness?.lightweight_available ? "选择这次怎么上线" : "配置产品需要的上线服务") : "准备线上版本"}</strong><small className="deployment-reconnect-description">{checkingResources ? "第 1 步 · 完成准备后，再看方案和费用" : "第 4 步 · 配置当前产品实际需要的服务"}</small></div></header>
      <p className="deployment-guide-intro">{productionReadiness?.lightweight_available ? "这个版本已完成轻量预览适配，可以只托管网页、不连接数据库。需要云端保存时仍可选择下方配置。" : "根据第三阶段已验证产品的实际依赖，逐项连接所需服务。必需的数据库或接口不能跳过；配置前请先查看用途、操作步骤和费用。"}</p>
      <ol>
        <li><span>{productionReadiness?.package_ready ? <Check size={14} /> : "1"}</span><p>产品版本检查：{productionReadiness?.package_ready ? `第 ${productionReadiness.code_version} 版已通过本地测试` : "等待完成线上版本适配"}</p></li>
        <li><span>{productionReadiness?.preview_accepted ? <Check size={14} /> : "2"}</span><p>新版试用确认：{productionReadiness?.preview_accepted ? "已确认" : "需要你试用并确认当前版本"}</p></li>
        <li><span>{light || productionReadiness?.database_connected ? <Check size={14} /> : "3"}</span><p>记录保存方式：{light ? "已选择轻量版 · 保存在当前浏览器，无需云数据库" : productionReadiness?.database_connected ? "云数据库已连接" : productionReadiness?.lightweight_available ? "待选择，本版本支持跳过云数据库" : "当前产品需要云数据库，尚未连接"}</p></li>
      </ol>
      {(!productionReadiness?.package_ready || !productionReadiness?.preview_accepted) && <a className="ghost-button" href={`/?project=${project.id}&phase=build&stage=m1c`}>返回预览，检查并准备上线<ArrowRight size={15} /></a>}
      {productionReadiness?.lightweight_available && <section className="deployment-lightweight-choice" aria-label="轻量上线选择"><strong>{light ? "已选择轻量上线" : "先有网址、产品能用"}</strong><p>不购买云数据库，产品交互和记录保存在当前浏览器。换设备不会同步，清除浏览器数据会丢失记录。托管、访问流量和自定义域名仍可能收费。</p>{!light && <button className="primary-button" type="button" disabled={busy || replying || !productionReadiness?.lightweight_available} onClick={() => void selectLightweight()}>{busy ? "正在准备…" : "跳过数据库，先上线轻量版"}<ArrowRight size={15} /></button>}{!productionReadiness?.lightweight_available && <p role="status">当前版本尚未完成轻量版适配，不能直接跳过服务依赖。请先在生成预览中准备浏览器保存版。</p>}</section>}
      <details className="deployment-database-option"><summary>{productionReadiness?.lightweight_available ? "我需要云端保存记录 · 查看数据库配置引导（可选）" : "配置产品需要的数据库 · 查看操作引导"}</summary>
      {(!productionReadiness?.database_connected || Boolean(productionReadiness?.missing_environment?.length)) && <form className="deployment-credential-form" autoComplete="off" onSubmit={(event) => {event.preventDefault(); void connectDatabase();}}>
        <div className="deployment-credential-heading"><strong>连接保存用户记录的数据库</strong></div>
        <DatabaseSetupGuide value={databaseUrl} onChange={setDatabaseUrl} lightweightAvailable={Boolean(productionReadiness?.lightweight_available)} />
        {(productionReadiness?.required_environment ?? []).filter((name) => !["APP_ENV", "DATABASE_URL", "STORAGE_MODE", "LIGHTWEIGHT_COMMIT"].includes(name)).map((name) => {
          const guide = productionReadiness?.service_guides?.[name];
          const entry = typeof guide?.console_url === "string" && guide.console_url.startsWith("https://") ? guide.console_url : null;
          return <section key={name} className="deployment-database-help"><strong>{guide?.title || `产品所需服务：${name}`}</strong><p>{guide?.purpose || "第三阶段声明此配置为必需项；具体供应商和用途尚待确认，请先核对方案，不要直接购买。"}</p>{entry && <a className="deployment-help-link" href={entry} target="_blank" rel="noreferrer">打开服务控制台<ArrowRight size={14} /></a>}{Array.isArray(guide?.steps) && <ol>{guide.steps.filter(step => typeof step === "string").map((step,index) => <li key={index}><span>{index+1}</span><p>{step}</p></li>)}</ol>}<p>{guide?.cost_note || "费用待确认，以对应服务的订单和计费规则为准。"}</p><button className="ghost-button" type="button" onClick={() => fillComposer(`请根据第三阶段产品说明，带我配置 ${name}：说明用途、供应商入口、费用、创建步骤和完成标志。`)}>带我配置这个服务</button><label>{name}<input type="password" autoComplete="new-password" value={additionalEnvironment[name] ?? ""} onChange={(event) => setAdditionalEnvironment((current) => ({...current, [name]: event.target.value}))} placeholder="只在这里填写对应服务的连接信息" /></label></section>;
        })}
        <p><LockKeyhole size={13} />只通过此表单填写，连接信息不会进入聊天或网页代码。</p>
        <button className="primary-button" type="submit" disabled={busy || replying || !databaseUrl.trim()}>{busy ? "正在验证数据库…" : "验证并安全保存"}</button>
      </form>}
      {productionReadiness?.database_connected && <p>数据库已连接，当前使用云端保存方式。</p>}
      </details>
      <button className="ghost-button" type="button" disabled={busy || replying} onClick={() => void load()}>刷新上线准备<RefreshCw size={15} /></button>
      <button className="primary-button" type="button" disabled={busy || replying || !productionReadiness?.ready} onClick={() => checkingResources || !authorizationUsable ? void quote() : setSelectedStepId("backend")}>{checkingResources || !authorizationUsable ? "准备完成，查看方案和费用" : "核对完成，继续正式发布"}<ArrowRight size={15} /></button>
    </section>;
  }

  function renderStepGuide() {
    const accountStep = selectedStep.id === "account";
    const identityStep = selectedStep.id === "identity";
    return <section className="deployment-connect-guide" aria-label="当前操作指引">
      <header><span><UserRound size={18} /></span><div><strong>{selectedStep.title}</strong><small>{accountStep || identityStep || selectedStep.id === "mvp" ? "这一步需要你操作" : "点线面检查后会告诉你结果"}</small></div></header>
      <p className="deployment-guide-intro">{selectedStep.summary}</p>
      <ol>{selectedStep.productActions.map((action, index) => <li key={action}><span>{index + 1}</span><p>{action}</p></li>)}</ol>
      <small className="deployment-connect-success">完成标志：{selectedStep.outcome}</small>
      {(accountStep || identityStep) ? <div className="deployment-guide-actions"><a className="primary-button" href="https://console.volcengine.com/" target="_blank" rel="noreferrer">{accountStep ? "打开火山引擎，注册或登录" : "打开控制台，查看实名认证"}<ArrowRight size={15} /></a><button type="button" className="ghost-button" disabled={busy || replying} onClick={() => { appendMessages({ role: "user", body: accountStep ? "我已登录火山引擎" : "我确认实名认证页面已显示通过" }); setSelectedStepId(accountStep ? "identity" : "access"); }}>{accountStep ? "我已登录，继续" : "页面显示认证通过，继续"}<ArrowRight size={15} /></button></div>
        : selectedStep.id === "inspect" ? <button type="button" className="primary-button" disabled={busy || replying || !realDeploymentAvailable} onClick={() => void quote()}>{busy ? "正在检查上线准备…" : "检查准备，继续查看方案和费用"}<ArrowRight size={15} /></button>
        : <button type="button" className="primary-button" disabled={busy || replying} onClick={() => void sendMessage(`请${selectedStep.title}。请先读取当前项目的真实状态，说明已验证和待确认的项目；需要我操作时，请给出入口、点击项、选择值和完成标志。`)}>检查这一步并告诉我结果<ArrowRight size={15} /></button>}
      {(accountStep || identityStep) && <a className="deployment-help-link" href="https://www.volcengine.com/docs/6261/64925" target="_blank" rel="noreferrer">查看官方注册与认证说明</a>}
      <button className="deployment-help-link" type="button" disabled={busy || replying} onClick={() => fillComposer(`我在“${selectedStep.title}”这一步卡住了，我看到的页面是：`)}>页面不一样 / 我卡住了</button>
    </section>;
  }

  function renderGatewayGuide() {
    const confirmedMissing = gatewayRequired;
    return <section className="deployment-connect-guide" aria-label="准备产品访问入口">
      <header><span><Globe2 size={18} /></span><div><strong>{confirmedMissing ? "还需要一个让别人访问产品的入口" : "先检查有没有可用的产品访问入口"}</strong><small>火山引擎把这个入口叫“API 网关”</small></div></header>
      <p className="deployment-guide-intro">{confirmedMissing ? "刚刚检查未找到本次发布可用的入口。需要你到火山引擎核对费用并确认创建。" : "之前的失败记录不代表现在仍然缺少入口。先检查现有服务，能复用就不用重新创建。"}</p>
      {confirmedMissing && <><ol>
        <li><span>1</span><p>打开下方创建页，地域选择<strong>{regionLabel}</strong>。当前指引支持北京地域。</p></li>
        <li><span>2</span><p>网关类型选择<strong>Serverless</strong>（控制台里的原名），网络选择<strong>公网</strong>，名称填写便于识别的产品名称。</p></li>
        <li><span>3</span><p>先核对页面的<strong>费用和服务条款</strong>，接受后再确认创建；不确定时停在这里，不要提交订单。</p></li>
        <li><span>4</span><p>等列表显示<strong>运行中</strong>后，回到这里点击“我已完成，重新检查”。</p></li>
      </ol><a className="primary-button" href="https://console.volcengine.com/veapig/region:veapig+cn-beijing/gateway/create" target="_blank" rel="noreferrer">去火山引擎查看入口和费用<ArrowRight size={15} /></a><small className="deployment-connect-success">完成标志：这里的检查通过，并出现本次发布的方案确认卡。</small></>}
      <button type="button" className="ghost-button wide" disabled={busy || replying || !realDeploymentAvailable} onClick={() => credential ? void quote() : setSelectedStepId("access")}>{busy ? "正在检查，不会创建收费服务…" : !credential ? "先安全连接账号" : confirmedMissing ? "我已完成，重新检查" : "检查现有入口和费用"}<RefreshCw size={15} /></button>
      {!realDeploymentAvailable && <p role="status">点线面的发布服务尚未就绪，先保留进度。请稍后在账号连接步骤重新检测。</p>}
    </section>;
  }

  function renderAccessControl() {
    if (selectedStep.id !== "access") return null;
    return (
      <>
        <div className="deployment-agent-control">
          {reconnecting || !credential ? (
            <>
              <section className="deployment-connect-guide deployment-account-instructions" aria-label="连接火山引擎账号">
                <header><span><KeyRound size={17} /></span><div><strong>重新连接火山引擎账号</strong><small className="deployment-reconnect-description">第 1 步 · 连接账号，检查上线准备</small></div></header>
                <p className="deployment-guide-intro">先在火山引擎登录本次要用的账号，再将连接信息填入下方安全表单。连接后检查准备情况，下一步再看方案和费用。</p>
                <a className="primary-button deployment-console-link" href="https://console.volcengine.com/iam/identitymanage/user" target="_blank" rel="noreferrer"><Globe2 size={15} />打开火山引擎，获取连接信息<ArrowRight size={15} /></a>
                <section className="deployment-connection-help" aria-label="获取连接信息的步骤"><h3>获取连接信息</h3>
                  <p>第一次使用，请先在火山引擎官网注册并完成实名认证。已有部署专用用户可以直接使用，无需重复创建。</p>
                <ol>
                  <li><span>1</span><div className="deployment-help-step"><p><strong>创建部署专用用户</strong></p><p>在“用户”页点击<strong>新建用户 → 通过用户名创建</strong>，用户名填写 <strong>product-deploy</strong> 或其他便于识别的名字。已有部署用户可直接进入该用户的“权限”页，按第 3 步补齐权限。</p></div></li>
                  <li><span>2</span><div className="deployment-help-step"><p><strong>设置访问方式</strong></p>
                    <div className="deployment-access-choices">
                      <p><strong>勾选：编程访问</strong>，让点线面通过 API 部署产品。</p>
                      <p><strong>不勾选：允许用户管理自己的 API 密钥</strong>。密钥由主账号管理，点线面不需要创建或删除密钥的权限。</p>
                      <p><strong>不勾选：控制台访问</strong>，部署专用用户不需要登录控制台。</p>
                    </div><p>检查以上 3 个选项后，点击<strong>下一步</strong>。</p></div></li>
                  <li><span>3</span><div className="deployment-help-step"><p><strong>逐项添加这 3 个权限策略</strong></p><DeploymentPolicyChecklist /></div></li>
                  <li><span>4</span><div className="deployment-help-step"><p><strong>创建用户，保存并填写连接信息</strong></p><p>在“审阅”页核对用户名、编程访问和上述策略，再确认创建。保存完成页提供的 <strong>Access Key ID（AK）</strong> 和 <strong>Secret Access Key（SK）</strong>，填入下方安全表单，点击<strong>安全连接云账号</strong>。</p><p>已有用户需要新密钥时，使用主账号进入<strong>用户 → 对应用户名 → 密钥 → 新建密钥</strong>。SK 请妥善保存，不要发到聊天里。</p></div></li>
                </ol>
                </section>
              </section>
              {platformCheckResult === "activation_required" && <section className="deployment-failure-guide" role="status"><strong>函数服务还差一次初始化授权</strong><p>火山引擎要求先创建 <code>ServiceRoleForVeFaaS</code> 服务关联角色。请用主账号进入函数服务首页，阅读“跨服务访问请求”的权限范围，确认后点击“立即授权”。</p><p>完成后返回，使用当前这组 AK/SK 再点“安全连接云账号”，无需重新创建密钥或增加部署用户权限。</p><a className="deployment-help-link" href="https://console.volcengine.com/vefaas" target="_blank" rel="noreferrer">打开函数服务，完成初始化授权<ArrowRight size={14} /></a></section>}
              {platformCheckResult === "permission_required" && <section className="deployment-failure-guide" role="status"><strong>还差操作权限，暂时没有连接成功</strong><p>请使用火山引擎主账号打开“用户管理”，选择刚创建的部署用户 → 权限 → 添加权限。按上方第 3 步逐项补齐部署策略，然后再点“安全连接云账号”。</p><p>若页面提示服务未开通，先进入函数服务（veFaaS），阅读服务授权内容后再决定是否同意。不要把所有服务的全部权限一起开放。</p><a className="deployment-help-link" href="https://console.volcengine.com/vefaas" target="_blank" rel="noreferrer">打开函数服务，查看是否需要授权</a></section>}
              {credential && <section className="deployment-connected"><CheckCircle2 size={18} /><div><strong>已保存云账号连接</strong><small>验证现有账号后即可继续检查上线准备。</small><button className="primary-button" type="button" disabled={busy || replying || !realDeploymentAvailable} onClick={() => void connectCloud(true)}>{busy ? "正在验证账号…" : "使用已保存账号验证并继续"}<ArrowRight size={15} /></button></div></section>}
              <form className="deployment-credential-form" autoComplete="off" onSubmit={(event) => { event.preventDefault(); void connectCloud(); }}>
                <div className="deployment-credential-heading"><strong>安全连接</strong></div>
                <label>授权编号（控制台中的 Access Key ID）<input type={showSecrets ? "text" : "password"} value={accessKey} onChange={(event) => setAccessKey(event.target.value)} minLength={8} name="cloud-connection-access-key" autoComplete="new-password" readOnly={activeCredentialField !== "access"} onFocus={() => setActiveCredentialField("access")} onBlur={() => setActiveCredentialField(null)} data-1p-ignore="true" data-lpignore="true" spellCheck={false} placeholder="粘贴部署子用户的 AK" /></label>
                <label>授权密码（控制台中的 Secret Access Key）<span><input type={showSecrets ? "text" : "password"} value={secretKey} onChange={(event) => setSecretKey(event.target.value)} minLength={8} name="cloud-connection-secret-key" autoComplete="new-password" readOnly={activeCredentialField !== "secret"} onFocus={() => setActiveCredentialField("secret")} onBlur={() => setActiveCredentialField(null)} data-1p-ignore="true" data-lpignore="true" spellCheck={false} placeholder="粘贴对应的 SK" /><button type="button" onClick={() => setShowSecrets((value) => !value)} aria-label="显示或隐藏授权信息">{showSecrets ? <EyeOff size={15} /> : <Eye size={15} />}</button></span></label>
                <p><LockKeyhole size={13} />授权信息会加密保存，提交后清空输入框，不会写入聊天。</p>
                <button className="primary-button" type="submit" disabled={busy || accessKey.length < 8 || secretKey.length < 8}><CloudUpload size={15} />{busy ? "正在安全连接…" : "安全连接云账号"}</button>
              </form>
            </>
          ) : (
            <>
              <div className={`deployment-connected ${credential.status === "verified" ? "" : "pending"}`}><CheckCircle2 size={18} /><div><strong>{credential.status === "verified" ? "云账号已连接并验证" : "云账号授权已安全保存"}</strong><small>{credential.masked_access_key} · {credential.service} · {credential.status === "verified" ? "身份校验通过" : "授权已保存，等待平台验证"}</small></div><StatusPill status={credential.status} /></div>
              {realDeploymentAvailable && credential.status === "verified" && <button className="primary-button wide" type="button" disabled={busy || replying} onClick={() => { setSelectedStepId("inspect"); }}>继续检查上线准备<ArrowRight size={15} /></button>}
              {(!realDeploymentAvailable || credential.status !== "verified") && (
                <section className="deployment-platform-status">
                  <header><div><strong>{realDeploymentAvailable ? "平台能力已开通，等待云账号授权" : "暂时无法继续上线"}</strong><small>{realDeploymentAvailable ? "点线面真实部署通道已恢复" : "已保留授权信息，账号是否可用仍需验证"}</small></div><span className="deployment-platform-badge"><i />{realDeploymentAvailable ? "账号待验证" : "平台暂未开通"}</span></header>
                  <div className="deployment-platform-explanation">
                    <p>{realDeploymentAvailable ? "已安装并接入官方 veFaaS CLI，你不需要重新填写 AK/SK。" : "点线面当前还没有启用真实云部署能力。你不需要配置服务器，也不需要重新填写 AK/SK。"}</p>
                    <p>{realDeploymentAvailable ? "点击下方按钮会只读检查账号身份和 veFaaS 权限，不会创建云资源。" : "平台能力开通后，Agent 会继续验证账号和部署权限；现在可以重新检测能力是否已经恢复。"}</p>
                    {platformCheckResult === "permission_required" ? (
                      <section className="deployment-permission-guide" aria-label="火山引擎权限配置向导">
                        <div className="deployment-permission-guide-heading">
                          <span><ShieldAlert size={16} /></span>
                          <div><strong>Agent 带你完成权限配置</strong><small>Agent 已定位问题；你只需登录主账号并确认授权</small></div>
                          <em>约 3 分钟</em>
                        </div>
                        <div className="deployment-capability-split" aria-label="部署任务分工">
                          <div><small>Agent 自动完成</small><strong>工具接入、凭证校验、问题定位</strong></div>
                          <div><small>Agent 准备，你来确认</small><strong>费用范围、发布内容与回滚目标</strong></div>
                          <div><small>确认后 Agent 执行</small><strong>发布、真实验收与需要时回滚</strong></div>
                          <div className="user"><small>必须由管理员完成</small><strong>主账号登录、服务开通、IAM 授权</strong></div>
                        </div>
                        <ol>
                          <li>
                            <span>1</span>
                            <div>
                              <strong>开通 veFaaS 服务角色</strong>
                              <p>使用火山引擎主账号打开服务授权页，点击<strong>同意授权 / 开通服务</strong>。</p>
                              <a href="https://console.volcengine.com/iam/service/attach_role/?ServiceName=vefaas" target="_blank" rel="noreferrer">打开服务授权页<ArrowRight size={14} /></a>
                              <small>完成标志：能够进入 veFaaS 控制台，不再提示服务未开通。</small>
                            </div>
                          </li>
                          <li>
                            <span>2</span>
                            <div>
                              <strong>给部署子用户添加权限</strong>
                              <p>进入<strong>用户管理</strong>，选择创建这组 AK/SK 的子用户，点击<strong>权限 → 添加权限</strong>。</p>
                              <DeploymentPolicyChecklist />
                              <div className="deployment-permission-links">
                                <a href="https://console.volcengine.com/iam/identitymanage/user" target="_blank" rel="noreferrer">打开用户管理<ArrowRight size={14} /></a>
                                <a href="https://www.volcengine.com/docs/6662/1355665" target="_blank" rel="noreferrer">查看最小权限清单<ArrowRight size={14} /></a>
                              </div>
                              <small>只给本次使用的部署专用用户添加权限。</small>
                            </div>
                          </li>
                          <li>
                            <span>3</span>
                            <div>
                              <strong>回来让 Agent 自动复检</strong>
                              <p>无需重新填写 AK/SK。完成前两步后，点击下方按钮，或在对话中说<strong>“权限已配置，重新验证”</strong>。</p>
                              <small>完成标志：状态变为“云账号已连接并验证”。</small>
                            </div>
                          </li>
                        </ol>
                        <div className="deployment-permission-boundary"><CheckCircle2 size={15} /><span><strong>Agent 已完成：</strong>安装部署工具、保存凭证并定位缺失权限</span></div>
                        <div className="deployment-permission-boundary user"><UserRound size={15} /><span><strong>需要你确认：</strong>主账号登录与 IAM 授权，Agent 不能替子用户给自己提权</span></div>
                        <button className="ghost-button wide" type="button" onClick={() => void recheckPlatformCapability()} disabled={busy || replying || checkingPlatform}><RefreshCw size={15} />{checkingPlatform ? "正在复检权限…" : "我已配置，重新验证"}<ArrowRight size={15} /></button>
                      </section>
                    ) : (
                      <>
                        {platformCheckResult === "unavailable" && <p className="deployment-platform-check-result" role="status"><CheckCircle2 size={15} />刚刚检测：平台能力仍未开通，无需重复操作</p>}
                        <button className="ghost-button wide" type="button" onClick={() => void recheckPlatformCapability()} disabled={busy || replying || checkingPlatform}><RefreshCw size={15} />{checkingPlatform ? "正在检测…" : realDeploymentAvailable ? "验证云账号权限" : "重新检测平台能力"}<ArrowRight size={15} /></button>
                      </>
                    )}
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      </>
    );
  }

  return (
    <section className="deployment-workbench" aria-label="上线部署工作台">
      <aside className="deployment-assistant-pane prd-assistant-pane codex-assistant-surface" aria-label="上线助手">
        <div ref={historyRef} className="codex-conversation-toolbar">
          <div className="codex-conversation-actions">
            {route && <button type="button" onClick={resetGuide} aria-label="重新选择账号状态" title="重新选择账号状态"><RotateCcw size={17} /></button>}
            <button type="button" onClick={() => setHistoryOpen((value) => !value)} aria-label="历史对话" aria-expanded={historyOpen} title="历史对话"><History size={18} /></button>
            <button type="button" onClick={createConversation} aria-label="新建对话" title="新建对话"><SquarePen size={17} /></button>
          </div>
          {historyOpen && (
            <div className="codex-history-popover" role="dialog" aria-label="历史对话">
              <div className="codex-history-heading"><strong>历史对话</strong><span>{conversationHistory.length} 条</span></div>
              <div className="codex-history-list">
                {conversationHistory.map((item) => (
                  <button key={item.id} type="button" className={item.id === activeConversationId ? "active" : ""} onClick={() => activateConversation(item.id)} aria-current={item.id === activeConversationId ? "true" : undefined}>
                    <span><strong>{item.title}</strong><small>{new Date(item.updatedAt).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })} · {item.messages.filter((message) => message.role === "user").length} 轮</small></span>
                    {item.id === activeConversationId && <i>当前</i>}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="codex-conversation-scroll">
          {!hasStartedConversation ? (
            <div className="codex-welcome deployment-codex-welcome">
              <div className="codex-welcome-heading">
                <span className="codex-welcome-mark"><CodexMark /></span>
                <h1><span>我是你的 AI 上线助手</span><span>帮你把产品真正发布到网上</span></h1>
              </div>
              <ul className="codex-guide-list" aria-label="上线助手能力">
                {DEPLOYMENT_STARTERS.map(({ label, icon: Icon }) => <li key={label}><Icon size={22} /><span>{label}</span></li>)}
              </ul>
            </div>
          ) : (
            <div className="prd-chat-thread codex-chat-thread deployment-codex-thread" aria-live="polite">
              <details className="deployment-step-conversation" open={conversationExpanded} onToggle={(event) => setConversationExpanded(event.currentTarget.open)}><summary>查看与上线助手的对话</summary>
              {messages.map((message) => (
                <Fragment key={message.id}>
                  <article className={message.role}><div className="codex-message-content"><p>{message.body}</p></div></article>
                  
                </Fragment>
              ))}
              </details>
              {replying && (
                <section className="prd-thinking-process is-thinking deployment-thinking" aria-label="上线助手正在分析" aria-live="polite">
                  <header><strong>上线助手正在分析</strong><span>已思考 {thinkingSeconds} 秒</span></header>
                  <ol><li className="active"><span><i /></span><p>正在检查你的部署情况</p></li></ol>
                </section>
              )}
              {!runtimeLoaded && !replying && <section className="deployment-connect-guide" role="status"><strong>正在读取这个产品的账号连接和发布记录</strong><p className="deployment-guide-intro">读取完成后，请重新连接本次上线使用的账号。</p><button className="ghost-button" type="button" onClick={() => void load()}>重新读取准备情况<RefreshCw size={15} /></button></section>}
              {runtimeLoaded && guideView.onboarding && !replying && (
                <section className="deployment-connect-guide" aria-label="重新连接账号">
                  <header><span><KeyRound size={18} /></span><div><strong>请重新连接你的火山引擎账号</strong><small className="deployment-reconnect-description">无论之前是否登录或连接过，都需要重新连接后继续。</small></div></header>
                  <p className="deployment-guide-intro">先连接账号并检查准备情况，再一起看方案和费用，最后由你确认本次操作权限。</p>
                  <button className="primary-button" type="button" disabled={busy || replying} onClick={reconnectAccount}>重新连接账号<ArrowRight size={15} /></button>
                </section>
              )}
              {route && !replying && ["address", "acceptance"].includes(selectedStep.id) && latest?.status !== "succeeded" && <section className="deployment-connect-guide deployment-stage-card"><header><span><Globe2 size={18} /></span><div><strong>{selectedStep.id === "acceptance" ? "领取网址和使用说明" : "检查实际使用效果"}</strong><small>请先完成第 5 步发布</small></div></header><p>当前还没有已成功发布的版本，请到右侧第 5 步查看进度或处理发布问题。</p></section>}
              {route && !replying && selectedStep.id === "access" && renderAccessControl()}
              {route && !replying && !["access", "backend", "gateway", "permissions", "operation_review", "online_code", "inspect", "address", "acceptance"].includes(selectedStep.id) && !showResult && renderStepGuide()}
              {route && !replying && ["permissions", "operation_review"].includes(selectedStep.id) && renderPlanReview()}
              {route && !replying && ["online_code", "inspect"].includes(selectedStep.id) && renderProductionPreparation()}
              {showGateway && !replying && renderGatewayGuide()}
              {route && selectedStep.id === "backend" && !replying && !["queued", "running", "succeeded"].includes(latest?.status ?? "") && (
                <div className="deployment-agent-control">
                  {!credential ? (
                    <button className="ghost-button wide" type="button" onClick={() => setSelectedStepId("access")}><KeyRound size={15} />先安全连接云账号<ArrowRight size={15} /></button>
                  ) : !realDeploymentAvailable ? (
                    <button className="ghost-button wide" type="button" disabled={busy || replying} onClick={() => setSelectedStepId("access")}>发布服务尚未就绪，查看连接状态<ArrowRight size={15} /></button>
                  ) : !authorizationUsable ? (
                    <button className="primary-button wide" type="button" onClick={() => void quote()} disabled={busy}><ShieldCheck size={15} />检查权限与真实费用<ArrowRight size={15} /></button>
                  ) : (
                    <div className="deployment-authorization"><div><span>发布产品<strong>{project.name}</strong></span><span>本次操作<strong>{resourcePlan.application_action === "update" ? "更新已有产品服务" : resourcePlan.application_action === "create" ? "创建产品运行服务" : "具体资源范围待确认"}</strong></span><span>发布位置<strong>{providerLabel} · {regionLabel}</strong></span><span>产品访问入口<strong>{gatewayLabel}</strong></span><span>预计费用<strong>{costLabel}</strong></span><span>确认有效期<strong>{formatDate(authorization!.expires_at)}</strong></span></div><p><ShieldAlert size={14} />本次会发布产品，并使用上述已有访问入口。费用未返回准确金额时，以火山引擎账单为准；确认前请先了解计费方式。</p><button className="primary-button wide" type="button" disabled={busy} onClick={() => void confirmAndDeploy()}>{busy ? "正在开始发布…" : "确认以上信息，正式发布"}<ArrowRight size={15} /></button></div>
                  )}
                </div>
              )}
              {latest && showResult && !replying && (
                <div className={`deployment-agent-control ${"deployment-handoff deployment-stage-card"}`}>
                  {selectedSkillStepIndex !== 5 && <div className={`deployment-live-result ${latest.status === "failed" ? "failed" : latest.status === "succeeded" ? "" : "pending"}`}><span><Server size={18} /></span><div><small>{latest.status === "simulated" ? "发布演练记录" : `第 ${latest.revision} 次发布记录`}</small><strong>{latest.status === "succeeded" ? latest.deployment_url ? selectedStep.id === "acceptance" ? "产品已上线，网址和使用说明已就绪" : "发布完成，继续检查实际使用效果" : "发布服务已返回完成，访问地址待确认" : latest.status === "simulated" ? "没有创建真实云资源" : latest.status === "failed" ? "这次发布没有完成" : "正在发布产品"}</strong></div><StatusPill status={latest.status} /></div>}
                  {selectedStep.id === "acceptance" && latest.status === "succeeded" && latest.deployment_url && typeof latest.evidence?.preview_image_url === "string" && latest.evidence.preview_image_url.startsWith("/deployment-previews/") && (
                    <a className="deployment-site-preview" href={latest.deployment_url} target="_blank" rel="noreferrer" aria-label={`预览并打开${project.name}`}>
                      <div className="deployment-preview-toolbar"><span><i /><i /><i /></span><small>网站缩览 · 本次发布实拍</small><ArrowRight size={15} /></div>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={latest.evidence.preview_image_url} alt={`${project.name}的线上网站画面`} loading="lazy" />
                      <div className="deployment-preview-caption"><strong>{project.name}</strong><span>点击图片，打开网站 ↗</span></div>
                    </a>
                  )}
                  {selectedStep.id === "acceptance" && (latest.deployment_url ? <a className="deployment-live-url" href={latest.deployment_url} target="_blank" rel="noreferrer"><Globe2 size={15} />{latest.deployment_url}<ArrowRight size={14} /></a> : <p className="deployment-no-url">{latest.status === "simulated" ? "模拟记录不会生成线上地址。" : latest.status === "failed" ? "本次未返回可用网址。是否已创建部分服务，需要检查发布记录后确认。" : "发布完成并通过 HTTPS 检查后，地址会出现在这里。"}</p>)}
                  {["queued", "running"].includes(latest.status) && <button className="ghost-button wide" type="button" onClick={() => void load()}><RefreshCw size={15} />刷新发布状态</button>}
                  {latest.status === "succeeded" && (selectedStep.id === "acceptance" ? (
                    <section className="deployment-result-acceptance" aria-label="第7步：网址和使用说明">
                      <header className="deployment-handoff-heading"><h3>网址和使用说明</h3><p>保存上方网址，即可随时访问或分享给其他人。</p></header>
                      <div className="deployment-handoff-grid">
                        <article><span className="deployment-handoff-label">01 / 开始使用</span><h4>如何使用产品</h4><p>{latest.evidence?.storage === "browser_local" ? "设置专注和休息时长，点击“开始专注”。计时中可以暂停、继续或提前结束，刷新页面会恢复当前计时。" : "按产品页面引导体验核心功能。登录方式和操作步骤，以当前产品的实际验收结果为准。"}</p></article>
                        <article><span className="deployment-handoff-label">02 / 数据保存</span><h4>{latest.evidence?.storage === "browser_local" ? "记录留在当前浏览器" : "确认记录保存方式"}</h4><p>{latest.evidence?.storage === "browser_local" ? "轻量预览版，无需登录或连接数据库。记录不会跨设备同步；清除浏览器数据后无法自动找回。" : "请核对本项目的数据存储、用户隔离和恢复能力。缺少验收证据的项目仍需确认。"}</p></article>
                      </div>
                      <section className="deployment-handoff-billing"><div><h4>费用与服务管理</h4><p>运行服务和访问入口可能持续计费，准确金额以火山引擎账单为准。停用时需核对本项目的函数和网关，关闭网页不会停止计费。</p></div><a href="https://console.volcengine.com/" target="_blank" rel="noreferrer">查看账单和服务<ArrowRight size={15} /></a></section>
                      <div className="deployment-finish-action">
                        {handoffComplete ? <p role="status"><Check size={18} />上线流程已完成，网址和使用说明可以随时回来查看。</p> : <button type="button" className="primary-button wide" onClick={() => { setCompletedDeploymentId(latest.id); setSelectedStepId("acceptance"); onNotice("上线流程已完成，网址和使用说明已保留。"); }}>完成，保存本次上线进度<Check size={16} /></button>}
                      </div>

                    </section>
                  ) : selectedSkillStepIndex === 4 ? (
                    <section className="deployment-result-acceptance" aria-label="发布你的产品"><header className="deployment-handoff-heading"><h3>发布你的产品</h3><p>第 5 步 · 查看本次发布的执行结果</p></header><div className="deployment-stage-grid"><div><h4>发布结果</h4><p>第 {latest.revision} 次发布已完成</p><small>{project.name}</small></div><div><h4>接下来做什么</h4><p>进入右侧第 6 步，打开线上产品试用核心功能。</p><small>查看本页不会重新发布。</small></div></div><button type="button" className="primary-button wide" onClick={() => setSelectedStepId("address")}>下一步，检查实际使用效果<ArrowRight size={15} /></button></section>
                  ) : (
                    <section className="deployment-result-acceptance" aria-label="检查实际使用效果">
                      <header className="deployment-handoff-heading"><h3>检查实际使用效果</h3><p>第 6 步 · 走一遍实际操作，发现问题及时反馈</p></header>
                      {latest.deployment_url && <a className="primary-button wide" href={latest.deployment_url} target="_blank" rel="noreferrer">打开网站，开始试用<ArrowRight size={15} /></a>}
                      <div className="deployment-stage-checks">
                        <div><span>01</span><div><h4>试用核心功能</h4><p>{latest.evidence?.storage === "browser_local" ? "开始一轮专注，依次点击暂停、继续、提前结束。" : "按第三阶段确认的核心流程完成一次操作；需要登录的产品请先登录。"}</p><small>看结果：按钮有响应，操作后出现对应结果。</small></div></div>
                        <div><span>02</span><div><h4>刷新后再看看</h4><p>{latest.evidence?.storage === "browser_local" ? "暂停计时后刷新页面，检查剩余时间和暂停状态是否保留。" : "保存一条记录后刷新，检查数据是否按产品约定保留。"}</p><small>看结果：页面正常恢复，没有意外丢失当前操作。</small></div></div>
                        <div><span>03</span><div><h4>换手机试一次</h4><p>在手机上打开网站，检查文字、按钮和核心操作。</p><small>看结果：文字能看清，按钮能点击，页面不被截断。</small></div></div>
                      </div>
                      <div className="deployment-stage-feedback"><h4>试用遇到问题？</h4><p>告诉助手“点了什么、预期是什么、实际发生了什么”，可以附上截图。</p><button className="ghost-button" type="button" onClick={() => fillComposer("线上试用遇到问题：我点击了……，预期……，实际……")}>填写问题反馈<ArrowRight size={15} /></button></div>
                      <button type="button" className="primary-button wide" onClick={() => { setCompletedStepIds((current) => [...new Set([...current, "address", "monitor"])]); setSelectedStepId("acceptance"); }}>下一步，领取网址和使用说明<ArrowRight size={15} /></button>
                    </section>
                  ))}
                  {latest.status === "failed" && (
                    <>
                      <section className="deployment-failure-guide" aria-label="发布失败原因与下一步">
                        <header><ShieldAlert size={18} /><div><strong>{latest.error_code === "CLOUD_API_GATEWAY_REQUIRED" ? "上次发布缺少产品访问入口" : "这次发布没有完成"}</strong><small>这是第 {latest.revision} 次发布的记录，不代表刚刚又执行了一次发布。</small></div></header>
                        <p>先检查当前情况，再决定如何继续。没有确认前，不会再次发布。</p>
                        <details><summary>查看技术原因</summary><p>错误码：{latest.error_code ?? "DEPLOYMENT_FAILED"}</p><p>{typeof latest.checkpoint?.failure_message === "string" ? latest.checkpoint.failure_message : "等待读取详细记录"}</p></details>
                        <button className="ghost-button wide" type="button" disabled={busy || replying} onClick={() => { setSelectedStepId(latest.error_code === "CLOUD_API_GATEWAY_REQUIRED" ? "gateway" : "inspect"); }}>检查并继续处理<ArrowRight size={15} /></button>
                      </section>
                      <div className="deployment-rollback"><RotateCcw size={15} />重试前先确认已创建的服务与可恢复版本，避免重复计费。</div>
                    </>
                  )}
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          )}
        </div>
        <form ref={composerRef} className="codex-command-composer deployment-codex-composer" onSubmit={(event) => { event.preventDefault(); void sendMessage(); }}>
          <button
            className="deployment-quick-prompt"
            type="button"
            onClick={() => fillComposer(deploymentPrompt)}
            disabled={busy || replying}
            aria-label={`填入指令：${deploymentPrompt}`}
          >
            {deploymentPrompt}
          </button>
          <div className="codex-composer-box">
            <textarea ref={messageDraftRef} value={messageDraft} onChange={(event) => setMessageDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void sendMessage(); } }} rows={1} placeholder={listening ? "正在聆听…" : "告诉我下一步想做什么，例如：帮我上线这个产品"} aria-label="向上线助手发送下一步指令" disabled={replying} />
            <div className="codex-composer-toolbar">
              <button className="codex-tool-button codex-add-button" type="button" onClick={() => fileInputRef.current?.click()} aria-label="添加文件" title="上传部署说明、代码或日志（不要上传密钥文件）" disabled={busy || replying}><Plus size={20} /></button>
              <input
                ref={fileInputRef}
                className="codex-file-input"
                type="file"
                hidden
                accept={SUPPORTED_UPLOAD_ACCEPT}
                disabled={busy || replying}
                onChange={(event) => {
                  const file = event.currentTarget.files?.[0];
                  event.currentTarget.value = "";
                  if (file) void uploadDeploymentFile(file);
                }}
              />
              <CodexModelSettings fastMode={fastMode} onFastModeChange={setFastMode} model={model} effort={reasoningEffort} onModelChange={setModel} onEffortChange={setReasoningEffort} open={openComposerMenu === "models"} onOpenChange={(open) => setOpenComposerMenu(open ? "models" : null)} disabled={busy || replying} />
                  <button className={`codex-tool-button codex-mic-button ${listening ? "listening" : ""}`} type="button" onClick={toggleDictation} aria-label={listening ? "停止听写" : "开始听写"} aria-pressed={listening} disabled={busy || replying}><Mic size={19} /></button>
              {replying ? <button className="codex-stop-button deployment-send-button" type="button" onClick={() => stopReplying(true)} aria-label="停止分析"><Square size={12} fill="currentColor" /></button> : <button className="codex-send-button deployment-send-button" type="submit" disabled={!messageDraft.trim() || busy} aria-label="发送给上线助手"><ArrowUp size={18} /></button>}
            </div>
          </div>
        </form>
      </aside>

      <aside className="deployment-skill-steps" aria-label={`上线步骤，共 ${SKILL_STEPS.length} 步`}>
        <header><span>部署上线</span><strong>上线共 {SKILL_STEPS.length} 步</strong></header>
        <ol>
          {SKILL_STEPS.map((step, index) => {
            const active = index === selectedSkillStepIndex && !(handoffComplete && index === 6);
            const done = handoffComplete || (!active && navigationProgress.enabled && (index <= completedThroughIndex || step.stepIds.every((id) => completedStepIds.includes(id))));
            return <li key={step.id} className={active ? "active" : done ? "done" : ""} aria-current={active ? "step" : undefined} aria-label={`${step.title}，${done ? "已完成" : active ? "进行中" : "未完成"}`}>
              <button type="button" aria-current={active ? "step" : undefined} disabled={busy || replying || !navigationProgress.enabled || index > navigationProgress.unlockedThrough} onClick={() => {
                if (!navigationProgress.enabled || index > navigationProgress.unlockedThrough) return;
                const destinations = ["inspect", "permissions", "operation_review", "online_code", "backend", "address", "acceptance"];
                setConversationExpanded(false);
                setBrowsingStepId(destinations[index]);
              }}>
                <span>{done ? <Check size={14} /> : index + 1}</span>
                <strong>{step.title}</strong>
              </button>
            </li>;
          })}
        </ol>
      </aside>
    </section>
  );
}
