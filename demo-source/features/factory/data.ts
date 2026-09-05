import {
  Boxes,
  Braces,
  CheckCircle2,
  ClipboardCheck,
  CloudUpload,
  FileUp,
  FileArchive,
  Gauge,
  Map,
  MonitorPlay,
  Rocket,
  type LucideIcon,
} from "lucide-react";

export type StageKey = "m1a" | "m1b" | "m1c" | "m1d" | "m2a" | "m2b" | "m2c" | "m3m4";

export type ProductPhaseKey = "idea" | "solution" | "build" | "launch";

export type ProductPhaseDefinition = {
  key: ProductPhaseKey;
  title: string;
  shortTitle: string;
  description: string;
  promise: string;
  icon: LucideIcon;
};

/**
 * The four phases are the public product contract. STAGES below remain the
 * internal production state machine and must not be used as primary navigation.
 */
export const PRODUCT_PHASES: ProductPhaseDefinition[] = [
  {
    key: "idea",
    title: "告诉我你想做什么",
    shortTitle: "上传点子或 PRD",
    description: "用一句话或现有文档开始，工厂会帮你补全真正需要确认的产品需求。",
    promise: "一份清楚、可确认的产品需求",
    icon: FileUp,
  },
  {
    key: "solution",
    title: "确认产品怎么做",
    shortTitle: "确认方案",
    description: "用低保真界面故事板走一遍关键操作，确认页面、状态和首版范围后，再生成高保真 UI。",
    promise: "一套可以点击走查的低保真方案",
    icon: ClipboardCheck,
  },
  {
    key: "build",
    title: "看着产品长出来",
    shortTitle: "生成与预览",
    description: "看清哪些产品成果真实完成、哪些仍待验证，再亲手体验与已确认需求一致的产品。",
    promise: "一个可以亲手操作的真实产品",
    icon: MonitorPlay,
  },
  {
    key: "launch",
    title: "把产品交到你手里",
    shortTitle: "部署与上线",
    description: "确认真实发布位置、账号授权和费用，完成发布并验证线上产品可以正常使用。",
    promise: "一个可访问、可验证的线上产品",
    icon: Rocket,
  },
];

export type StageDefinition = {
  key: StageKey;
  code: string;
  title: string;
  shortTitle: string;
  description: string;
  promise: string;
  icon: LucideIcon;
};

export const STAGES: StageDefinition[] = [
  {
    key: "m1a",
    code: "M1A",
    title: "把想法说清楚",
    shortTitle: "需求与方案",
    description: "补全需求，生成并确认 PRD 与产品方案。",
    promise: "产品想法进入规范开发流程",
    icon: Braces,
  },
  {
    key: "m1b",
    code: "M1B",
    title: "先把产品走一遍",
    shortTitle: "产品地图",
    description: "用产品地图、关键决策与虚拟用户走查提前发现问题。",
    promise: "用可视化方式看懂产品",
    icon: Map,
  },
  {
    key: "m1c",
    code: "M1C",
    title: "让 AI 受控开发",
    shortTitle: "自动开发",
    description: "查看代码生成、工具执行、版本与隔离工作区。",
    promise: "平台真正开始生成产品代码",
    icon: Boxes,
  },
  {
    key: "m1d",
    code: "M1D",
    title: "边体验，边修好",
    shortTitle: "测试与预览",
    description: "自动测试、有限修复、真实预览和反馈改版。",
    promise: "获得真正可操作的产品预览",
    icon: CheckCircle2,
  },
  {
    key: "m2a",
    code: "M2A",
    title: "每一笔消耗都看得见",
    shortTitle: "额度与模型",
    description: "安全连接模型 Key，查看额度、用量、成本与审计。",
    promise: "额度不足会暂停，Key 不会泄漏",
    icon: Gauge,
  },
  {
    key: "m2b",
    code: "M2B",
    title: "确认后再正式上线",
    shortTitle: "授权与部署",
    description: "连接云账号、确认权限和费用、部署与回滚。",
    promise: "产品正式发布到互联网",
    icon: CloudUpload,
  },
  {
    key: "m2c",
    code: "M2C",
    title: "真正拿走你的产品",
    shortTitle: "完整交付",
    description: "下载源码、文档、测试报告，并按需同步 GitHub。",
    promise: "拿到代码、文档和线上地址",
    icon: FileArchive,
  },
  {
    key: "m3m4",
    code: "M3/M4",
    title: "从能用到多人稳定使用",
    shortTitle: "稳定运营",
    description: "数据库、备份、监控、限流、邀请码与内测运营。",
    promise: "支持真实案例与多人内测",
    icon: Gauge,
  },
];

const PROJECT_STAGE_INDEX: Record<string, number> = {
  REQUIREMENTS: 0,
  PRD_REVIEW: 0,
  SOLUTION_REVIEW: 0,
  DEVELOPMENT: 2,
  PAUSED: 3,
  PREVIEW_REVIEW: 3,
  DEPLOYMENT: 5,
  DELIVERY: 6,
};

const PROJECT_PHASE_INDEX: Record<string, number> = {
  REQUIREMENTS: 0,
  PRD_REVIEW: 0,
  SOLUTION_REVIEW: 1,
  DEVELOPMENT: 2,
  PAUSED: 2,
  PREVIEW_REVIEW: 2,
  DEPLOYMENT: 3,
  DELIVERY: 3,
  COMPLETED: 3,
  OPERATIONS: 3,
};

export function getCurrentStageIndex(projectStage: string): number {
  return PROJECT_STAGE_INDEX[projectStage] ?? 0;
}

export function getCurrentPhaseIndex(projectStage: string): number {
  return PROJECT_PHASE_INDEX[projectStage] ?? 0;
}

export function getPhaseForStage(stage: StageKey, projectStage?: string): ProductPhaseKey {
  if (stage === "m1a") return projectStage === "SOLUTION_REVIEW" ? "solution" : "idea";
  if (stage === "m1b") return "solution";
  if (["m1c", "m1d", "m2a"].includes(stage)) return "build";
  return "launch";
}

export function getDefaultStageForPhase(phase: ProductPhaseKey, projectStage: string): StageKey {
  if (phase === "idea") return "m1a";
  if (phase === "solution") {
    return ["REQUIREMENTS", "PRD_REVIEW", "SOLUTION_REVIEW"].includes(projectStage) ? "m1a" : "m1b";
  }
  if (phase === "build") {
    return "m1c";
  }
  return "m2b";
}

export const STATUS_TEXT: Record<string, string> = {
  idle: "尚未开始",
  queued: "已进入队列",
  running: "正在执行",
  succeeded: "已完成",
  partially_succeeded: "部分完成",
  failed: "执行失败",
  cancelled: "已取消",
  disconnected: "连接中断",
  stale: "状态待刷新",
  ready: "已准备好",
  draft: "草稿",
  active: "进行中",
  open: "等待确认",
  confirmed: "已确认",
  passed: "已通过",
  simulated: "模拟完成",
  paused: "已暂停",
  unverified: "待验证",
  verified: "已验证",
  expired: "已过期",
  revoked: "已撤销",
};

export function statusText(status?: string | null): string {
  if (!status) return "尚未开始";
  return STATUS_TEXT[status.toLowerCase()] ?? status;
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
