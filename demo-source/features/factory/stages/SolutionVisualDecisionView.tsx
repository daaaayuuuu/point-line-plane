"use client";

import { useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Bell, MousePointerClick, Pause, Play, RotateCcw } from "lucide-react";
import type { JsonObject, LowFidelityPrototypeContract } from "@/lib/api/types";
import { UiStylePicker, loadUiStylePreference, saveUiStylePreference, type UiStyleKey } from "../UiStylePicker";

type StoryFrame = {
  key: string;
  eyebrow: string;
  title: string;
  description: string;
  action: string;
  result: string;
  source: string;
  sources: string[];
  sourceSection: "端到端流程" | "功能要求";
  requirements: string[];
  confirmation: "已确认" | "待确认" | "PRD 约定";
  timer?: string;
  focusTimer?: string;
  breakTimer?: string;
  mode?: "focus" | "pause" | "short-break" | "alert";
  phase?: string;
  completionMessage?: string;
  statusNote?: string;
  focusLabel?: "专注" | "学习";
  supportsPause?: boolean;
  supportsReset?: boolean;
  supportsEarlyEnd?: boolean;
  confirmsEarlyEnd?: boolean;
  secondaryAction?: string;
  view?: "timer" | "notice" | "summary" | "setup" | "generic";
  surface: string;
  nextSurface?: string;
};

type SolutionVisualDecisionViewProps = {
  projectId: string;
  prdContent: JsonObject;
};

type FrameSeed = {
  sources: string[];
  sourceSection: StoryFrame["sourceSection"];
  requirements: string[];
  surface: string;
  nextSurface?: string;
};

const MATCH_TERMS = [
  "首次", "默认", "进入", "打开", "开始", "运行", "暂停", "继续", "重置", "显示", "剩余时间",
  "运行状态", "归零", "结束", "切换", "下一阶段", "主动开始", "自动开始", "页面内提醒", "提醒",
  "提示音", "声音", "通知", "授权", "自然完成", "完整专注", "完成次数", "记录", "统计", "刷新",
  "离开", "恢复", "本地", "主题", "可读性", "设置", "偏好", "权限",
];

function recordOf(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}

function linesOf(...values: unknown[]): string[] {
  const result: string[] = [];
  const visit = (value: unknown) => {
    if (Array.isArray(value)) value.forEach(visit);
    else if (typeof value === "string" && value.trim()) result.push(value.trim().replace(/[。.]+$/g, ""));
  };
  values.forEach(visit);
  return [...new Set(result)];
}

function confirmationOf(...sources: Array<string | undefined>): StoryFrame["confirmation"] {
  const text = sources.filter(Boolean).join(" ");
  if (text.includes("待确认")) return "待确认";
  if (text.includes("已确认")) return "已确认";
  return "PRD 约定";
}

function cleanRequirement(value: string): string {
  return value
    .replace(/^(?:FR|NFR)-\d+【(?:已确认|待确认)】：/i, "")
    .replace(/^(?:FR|NFR)-\d+[：:]?/i, "")
    .replace(/^(?:已确认|待确认)(?:的建议)?[：:]/, "")
    .trim();
}

function shortTitle(value: string): string {
  const cleaned = cleanRequirement(value)
    .replace(/^用户/, "")
    .replace(/^系统/, "")
    .replace(/[；。].*$/, "")
    .trim();
  return cleaned.length > 26 ? `${cleaned.slice(0, 26)}…` : cleaned || "待确认";
}

function productNameFromFullDocument(full: JsonObject): string {
  const title = typeof full.document_title === "string" ? full.document_title.trim() : "";
  const cleaned = title
    .replace(/[（(](?:新版|首版|第[^）)]*版)[）)]\s*$/i, "")
    .replace(/(?:[｜|·—-]\s*)?(?:Web\s*)?(?:首版|新版)?(?:产品需求文档|需求文档|PRD)\s*$/i, "")
    .replace(/[｜|·—-]\s*$/, "")
    .trim();
  return cleaned || title || "待确认产品";
}

function durationClock(lines: string[], kind: "focus" | "break"): string | undefined {
  const directPatterns = kind === "focus"
    ? [/(?:专注|学习|focus)(?:时间|时长|阶段)?[^\d]{0,8}(\d+)\s*分钟/i, /(\d+)\s*分钟(?:的)?(?:专注|学习|focus)/i]
    : [/(?:休息|break)(?:时间|时长|阶段)?[^\d]{0,8}(\d+)\s*分钟/i, /(\d+)\s*分钟(?:的)?(?:休息|break)/i];
  const clockPattern = kind === "focus"
    ? /(?:专注|学习|focus)(?:时间|时长|阶段)?[^\d]{0,8}(\d{1,2}):(\d{2})/i
    : /(?:休息|break)(?:时间|时长|阶段)?[^\d]{0,8}(\d{1,2}):(\d{2})/i;
  const rankedLines = lines.toSorted((a, b) => Number(/默认|初始|预设/.test(b)) - Number(/默认|初始|预设/.test(a)));
  for (const line of rankedLines) {
    for (const directPattern of directPatterns) {
      const direct = line.match(directPattern);
      if (direct && (!/范围|最小|最大|\d\s*[～~至-]\s*\d/.test(line) || /默认|初始|预设|固定/.test(line))) {
        return `${String(Number(direct[1])).padStart(2, "0")}:00`;
      }
    }
    const clock = line.match(clockPattern);
    if (clock) return `${clock[1].padStart(2, "0")}:${clock[2]}`;
  }
  return undefined;
}

function matchScore(requirement: string, flowItem: string): number {
  const requirementText = cleanRequirement(requirement).toLowerCase();
  const flowText = cleanRequirement(flowItem).toLowerCase();
  const keywordScore = MATCH_TERMS.reduce((score, term) => (
    requirementText.includes(term.toLowerCase()) && flowText.includes(term.toLowerCase()) ? score + term.length * 3 : score
  ), 0);
  const latinTokens = requirementText.match(/[a-z][a-z0-9_-]{2,}/g) ?? [];
  const latinScore = latinTokens.reduce((score, token) => flowText.includes(token) ? score + token.length : score, 0);
  return keywordScore + latinScore;
}

function surfaceFromText(value: string, fallbackIndex: number, forceTimerContext = false): string {
  const text = cleanRequirement(value).toLowerCase();
  const timerContext = forceTimerContext || /番茄|倒计时|计时|专注|休息|focus|break/.test(text);

  if (timerContext) {
    if (/输入|调整|修改.{0,6}时长|时长设置|默认值|必填|数字格式|范围校验|保存.{0,12}(?:专注|学习|休息)时长/.test(text)) return "timer-setup";
    if (/(?:显示|查看|展示|查询).{0,20}(?:当日|当天|今日|自然日|历史|记录|统计|完成次数|专注次数)|(?:当日|当天|今日|自然日|历史|统计).{0,20}(?:显示|展示|记录|次数)/.test(text) && !/倒计时.{0,8}完成|完成次数.{0,4}加/.test(text)) return "timer-records";
    const explicitlyCountsCompletion = /(?:自然|完整).{0,12}完成.{0,16}(?:增加|记录|计入|计数)|自然.{0,12}(?:归零|结束).{0,16}(?:增加|记录|计入|计数)/.test(text);
    const preventsDuplicateCompletion = /重复完成事件|同一(?:专注|学习|计时).{0,12}最多记录一次/.test(text);
    const positivelyUpdatesCount = !/不增加|不得增加|不会增加|不计入/.test(text)
      && /完成.{0,12}(?:增加|记录|计入|计数)|(?:增加|记录|计入).{0,8}(?:完成次数|专注次数)/.test(text);
    if (explicitlyCountsCompletion || preventsDuplicateCompletion || positivelyUpdatesCount) return "timer-complete";
    if (/阶段切换后|自动开始下一阶段|等待用户.{0,8}开始下一阶段/.test(text)) return "timer-complete";
    if (/当前阶段|运行中的计时|暂停状态/.test(text) && /开始|倒计时|暂停|继续|重置|结束/.test(text)) return "timer-focus";
    const restCompleted = /休息(?:阶段|时间)?.{0,10}(?:归零|结束|完成)|休息归零/.test(text);
    const focusCompleted = /(?:专注|学习)(?:阶段|时间)?.{0,10}(?:归零|结束|完成)|(?:专注|学习)倒计时归零/.test(text);
    if ((focusCompleted && !restCompleted) || /每个阶段完成后|计时完成时|阶段结束时/.test(text)) return "timer-complete";
    if (/休息/.test(text) && /开始|剩余|进度|暂停|继续|归零|完成|下一轮/.test(text)) return "timer-break";
    if (/完成|归零|提醒|通知|声音|振动/.test(text) && !/后台恢复|恢复前台/.test(text)) return "timer-complete";
    if (/开始|运行|阶段|剩余|进度|暂停|继续|提前结束|后台|恢复|时间戳|下一轮|重新进入|首次|默认|初始化|打开/.test(text)) return "timer-focus";
  }

  if (/登录|注册|验证码|sign[ -]?in|log[ -]?in/.test(text)) return "auth";
  if (/首次使用|引导|欢迎|初始化|onboarding/.test(text)) return "onboarding";
  if (/设置|偏好|权限|配置/.test(text)) return "settings";
  if (/统计|报表|历史|记录|看板|仪表盘/.test(text)) return "records";
  if (/搜索|筛选|列表|浏览|首页/.test(text)) return "browse-list";
  if (/详情|查看|预览/.test(text)) return "detail";
  if (/新建|创建|编辑|填写|输入|上传/.test(text)) return "edit-form";
  if (/确认|审核|提交|发布|支付/.test(text)) return "review-submit";
  if (/成功|完成|结果|失败|异常|错误/.test(text)) return "result-feedback";
  return `flow-${fallbackIndex}`;
}

function surfaceTitle(surface: string, fallback: string, focusLabel = "专注"): string {
  const titles: Record<string, string> = {
    "timer-setup": "首页与时长设置",
    "timer-focus": `${focusLabel}计时与状态控制`,
    "timer-break": "休息计时与下一轮",
    "timer-complete": `${focusLabel}完成与提醒`,
    "timer-records": "当日记录",
    auth: "账号与身份验证",
    onboarding: "首次使用引导",
    settings: "设置与偏好",
    records: "记录与统计",
    "browse-list": "浏览与列表",
    detail: "详情与预览",
    "edit-form": "创建与编辑",
    "review-submit": "确认与提交",
    "result-feedback": "结果与反馈",
  };
  return titles[surface] ?? shortTitle(fallback);
}

function mergeSeedsBySurface(seeds: FrameSeed[]): FrameSeed[] {
  const merged: FrameSeed[] = [];
  seeds.forEach((seed) => {
    const canMerge = !seed.surface.startsWith("flow-");
    const existing = canMerge ? merged.find((item) => item.surface === seed.surface) : undefined;
    if (!existing) {
      merged.push({ ...seed, sources: [...seed.sources], requirements: [...seed.requirements] });
      return;
    }
    existing.sources = linesOf(existing.sources, seed.sources);
    existing.requirements = linesOf(existing.requirements, seed.requirements);
  });
  merged.forEach((seed) => {
    const firstIndex = seeds.findIndex((item) => item.surface === seed.surface);
    seed.nextSurface ??= seeds.slice(firstIndex + 1).find((item) => item.surface !== seed.surface)?.surface;
  });
  return merged;
}

function seedsFromFullDocument(full: JsonObject): FrameSeed[] {
  const flow = linesOf(full.end_to_end_loop);
  const requirements = linesOf(full.functional_requirements);
  const isTimerProduct = /番茄|倒计时|计时器|专注.{0,8}休息|\d+\s*分钟专注/.test(JSON.stringify(full));
  if (flow.length === 0) {
    return mergeSeedsBySurface(requirements.map((source, index) => ({
      sources: [source],
      sourceSection: "功能要求",
      requirements: [source],
      surface: surfaceFromText(source, index, isTimerProduct),
    })));
  }

  const seeds: FrameSeed[] = flow.map((source, index) => ({
    sources: [source],
    sourceSection: "端到端流程",
    requirements: [],
    surface: surfaceFromText(source, index, isTimerProduct),
  }));
  requirements.forEach((requirement) => {
    const requirementSurface = surfaceFromText(requirement, -1, isTimerProduct);
    const canBeStandaloneUserView = ["timer-records", "records"].includes(requirementSurface);
    const existingSurfaceIndex = seeds.findIndex((seed) => seed.surface === requirementSurface);
    if (!requirementSurface.startsWith("flow-") && existingSurfaceIndex >= 0) {
      seeds[existingSurfaceIndex].requirements = linesOf(seeds[existingSurfaceIndex].requirements, requirement);
      return;
    }
    if (canBeStandaloneUserView && existingSurfaceIndex < 0) {
      seeds.push({
        sources: [requirement],
        sourceSection: "功能要求",
        requirements: [requirement],
        surface: requirementSurface,
        nextSurface: isTimerProduct ? "timer-focus" : undefined,
      });
      return;
    }
    let bestIndex = 0;
    let bestScore = Number.NEGATIVE_INFINITY;
    flow.forEach((flowItem, index) => {
      const sameSurface = seeds[index].surface === requirementSurface && !requirementSurface.startsWith("flow-");
      const score = matchScore(requirement, flowItem) + (sameSurface ? 18 : 0);
      if (score > bestScore) {
        bestIndex = index;
        bestScore = score;
      }
    });
    seeds[bestIndex].requirements.push(requirement);
  });
  return mergeSeedsBySurface(seeds);
}

function modeFromText(value: string): StoryFrame["mode"] {
  const text = cleanRequirement(value);
  if (/提醒|提示音|通知|完成次数|记录一次|计数/.test(text)) return "alert";
  if (/暂停/.test(text) && !/归零|结束/.test(text)) return "pause";
  if (/休息.*(?:归零|结束).*专注|切回.*专注|下一轮.*专注/.test(text)) return "focus";
  if (/专注.*(?:归零|结束).*休息|进入.*休息|切换到.*休息/.test(text)) return "short-break";
  const focusIndex = text.search(/专注|学习|focus/i);
  const breakIndex = text.search(/休息|break/i);
  if (breakIndex >= 0 && (focusIndex < 0 || breakIndex < focusIndex)) return "short-break";
  return "focus";
}

function viewFromText(value: string): StoryFrame["view"] {
  if (/完成次数|统计|计数|记录一次/.test(value)) return "summary";
  if (/提醒|提示音|系统通知|页面内/.test(value)) return "notice";
  return "timer";
}

function viewFromSurface(surface: string, sourceText: string): StoryFrame["view"] {
  if (surface === "timer-setup") return "setup";
  if (surface === "timer-records" || surface === "records") return "summary";
  if (surface === "timer-complete") return "notice";
  if (surface === "timer-focus" || surface === "timer-break") return "timer";
  return viewFromText(sourceText);
}

function modeFromSurface(surface: string, sourceText: string): StoryFrame["mode"] {
  if (surface === "timer-complete") return "alert";
  if (surface === "timer-break") return "short-break";
  if (surface === "timer-setup" || surface === "timer-focus" || surface === "timer-records") return "focus";
  return modeFromText(sourceText);
}

function actionFromSurface(surface: string, focusLabel: string, fallback: string, transitionPending: boolean): string {
  if (surface === "timer-setup") return `开始${focusLabel}`;
  if (surface === "timer-focus") return "查看计时结束";
  if (surface === "timer-complete") return transitionPending ? "进入休息（方式待确认）" : "开始休息";
  if (surface === "timer-break") return transitionPending ? `进入下一轮${focusLabel}（方式待确认）` : `开始下一轮${focusLabel}`;
  if (surface === "timer-records") return "返回计时";
  return actionFromText(fallback);
}

function actionFromText(value: string): string {
  const text = cleanRequirement(value);
  const quotedAction = text.match(/(?:点击|选择|提交|确认|打开)[“"]([^”"]+)[”"]/);
  if (quotedAction) return quotedAction[1];
  if (/开始.{0,8}休息|手动开始休息/.test(text)) return "开始休息";
  if (/开始.{0,8}(?:下一轮)?专注|手动开始下一轮/.test(text)) return "开始专注";
  if (/暂停.*继续.*重置/.test(text)) return "暂停 / 继续 / 重置";
  if (/重置/.test(text)) return "重置";
  if (/暂停/.test(text)) return "暂停";
  if (/继续/.test(text)) return "继续";
  if (/开始/.test(text)) return "开始";
  if (/提醒|通知/.test(text)) return "确认提醒";
  if (/记录|统计|完成次数/.test(text)) return "查看记录";
  if (/切换|下一阶段|下一轮/.test(text)) return "进入下一阶段";
  if (/进入|打开/.test(text)) return "进入产品";
  return "查看下一步";
}

function frameClock(source: string, mode: StoryFrame["mode"], focusClock: string, breakClock: string): string {
  const direct = durationClock([source], mode === "short-break" ? "break" : "focus");
  if (direct) return direct;
  if (mode === "alert") return "00:00";
  if (mode === "short-break") return breakClock;
  return focusClock;
}

function framesFromFullDocument(full: JsonObject): StoryFrame[] {
  const seeds = seedsFromFullDocument(full);
  const fullText = JSON.stringify(full);
  const tracksCompletedSessions = /完成次数|专注次数|完成记录|计数/.test(fullText);
  const learningMentions = (fullText.match(/学习/g) ?? []).length;
  const focusMentions = (fullText.match(/专注/g) ?? []).length;
  const focusLabel: "专注" | "学习" = learningMentions > focusMentions ? "学习" : "专注";
  const supportsPause = /暂停/.test(fullText) && /继续|恢复/.test(fullText);
  const supportsReset = /重置|归零当前|恢复当前阶段.*(?:默认|初始)/.test(fullText);
  const supportsEarlyEnd = /提前结束|请求结束|结束当前阶段/.test(fullText);
  const confirmsEarlyEnd = supportsEarlyEnd && /二次确认|确认后|避免误触/.test(fullText);
  const transitionPending = /待确认.{0,32}(?:自动开始|主动开始|等待用户)|阶段切换后.{0,32}(?:或自动开始|方式待确认)/.test(fullText);
  const durationSources = linesOf(
    full.inputs,
    full.domain_knowledge,
    full.constraints,
    full.functional_requirements,
    full.data_and_state,
  );
  const focusClock = durationClock(durationSources, "focus") ?? "待确认";
  const breakClock = durationClock(durationSources, "break") ?? "待确认";

  return seeds.map((seed, index) => {
    const primarySource = seed.sources[0];
    const sourceText = seed.sources.join("；");
    const relatedText = [sourceText, ...seed.requirements].join(" ");
    const nextSeed = seeds.find((item) => item.surface === seed.nextSurface) ?? seeds[index + 1];
    const next = nextSeed?.sources[0];
    const mode = modeFromSurface(seed.surface, sourceText);
    const action = actionFromSurface(seed.surface, focusLabel, next ?? sourceText, transitionPending);
    const description = seed.surface === "timer-complete"
      ? transitionPending
        ? `本轮${focusLabel}结束后会显示完成结果；下一阶段是等待用户开始还是自动开始，仍按 PRD 标记为待确认。`
        : tracksCompletedSessions
        ? `本轮${focusLabel}结束后，页面会明确显示完成结果、更新今日次数，并让用户自己选择何时开始休息。`
        : "本轮计时结束后，页面会明确显示完成结果，并让用户自己选择下一步操作。"
      : seed.surface === "timer-records"
        ? /仅展示当日|不承诺长期历史|不提供长期历史/.test(fullText)
          ? "显示今天已经完成的专注次数；首版只看当天，不提供长期历史记录。"
          : "展示用户已经完成的专注记录和统计结果。"
        : seed.sources.map(cleanRequirement).join("；");
    return {
      key: `${seed.sourceSection === "端到端流程" ? "flow" : "requirement"}-${index + 1}`,
      eyebrow: `界面 ${index + 1} · ${seed.sourceSection}`,
      title: surfaceTitle(seed.surface, primarySource, focusLabel),
      description,
      action,
      result: seed.surface === "timer-records"
        ? "返回计时页面，不改变当前计时状态和完成次数"
        : next ? cleanRequirement(next) : "完成完整 PRD 描述的本轮交互闭环",
      source: sourceText,
      sources: seed.sources,
      sourceSection: seed.sourceSection,
      requirements: seed.requirements,
      confirmation: confirmationOf(...seed.sources, ...seed.requirements),
      timer: frameClock(sourceText, mode, focusClock, breakClock),
      focusTimer: focusClock,
      breakTimer: breakClock,
      mode,
      phase: seed.surface === "timer-setup"
        ? "等待开始"
        : seed.surface === "timer-records"
          ? "查看记录"
          : seed.surface === "timer-break"
            ? "休息计时"
            : seed.surface === "timer-complete"
              ? `${focusLabel}完成`
              : seed.surface === "timer-focus"
                ? `${focusLabel}计时`
                : mode === "pause" ? "已暂停" : focusLabel,
      completionMessage: tracksCompletedSessions ? "今日完成次数已增加 1 次" : "本轮计时已经结束",
      statusNote: seed.surface === "timer-break"
        ? /休息.{0,12}(?:不增加|不得增加|不计入).{0,8}(?:次数|计数)/.test(fullText)
          ? `休息结束后会提醒，但不会增加${focusLabel}次数`
          : `休息结束后进入下一轮${focusLabel}`
        : undefined,
      focusLabel,
      supportsPause,
      supportsReset,
      supportsEarlyEnd,
      confirmsEarlyEnd,
      secondaryAction: !seed.surface.startsWith("timer-") && /重置/.test(relatedText) && action !== "重置" ? "重置" : undefined,
      view: viewFromSurface(seed.surface, sourceText),
      surface: seed.surface,
      nextSurface: seed.nextSurface,
    };
  });
}

export function buildLowFidelityPrototypeContract(prdContent: JsonObject): LowFidelityPrototypeContract {
  const fullDocument = recordOf(prdContent.full_document);
  const derivedFrames = Object.keys(fullDocument).length > 0
    ? framesFromFullDocument(fullDocument)
    : [missingFullDocumentFrame()];
  const frames = derivedFrames.length > 0 ? derivedFrames : [missingFullDocumentFrame()];
  return {
    schema_version: "low_fidelity_prototype_v1",
    source: "prd.full_document",
    source_document_title: typeof fullDocument.document_title === "string"
      ? fullDocument.document_title
      : "完整 PRD 待补齐",
    merge_policy: "merge_user_interfaces_preserve_requirements",
    screens: frames.map((frame) => ({
      key: frame.key,
      surface: frame.surface,
      title: frame.title,
      description: frame.description,
      primary_action: frame.action,
      resulting_state: frame.result,
      confirmation: frame.confirmation,
      source_items: frame.sources,
      functional_requirements: frame.requirements,
    })),
    coverage: {
      end_to_end_loop: linesOf(fullDocument.end_to_end_loop),
      functional_requirements: linesOf(fullDocument.functional_requirements),
    },
  };
}

function missingFullDocumentFrame(): StoryFrame {
  return {
    key: "missing-full-document",
    eyebrow: "完整 PRD 待补齐",
    title: "暂不生成原型",
    description: "当前 PRD 没有可供下游读取的 full_document，已停止回退到白盒摘要。",
    action: "等待完整 PRD",
    result: "补齐并确认完整 PRD 后，再据此生成界面故事板。",
    source: "prd.content.full_document 缺失",
    sources: ["prd.content.full_document 缺失"],
    sourceSection: "功能要求",
    requirements: [],
    confirmation: "待确认",
    view: "generic",
    surface: "missing",
  };
}

function TimerWireframe({ frame, productName, navigation, onAdvance, onNavigate }: { frame: StoryFrame; productName: string; navigation: string[]; onAdvance: () => void; onNavigate: (intent: string) => void }) {
  const [runtimeState, setRuntimeState] = useState<"idle" | "running" | "paused">("running");
  const [confirmingEarlyEnd, setConfirmingEarlyEnd] = useState(false);
  const focusLabel = frame.focusLabel ?? "专注";
  const isClockView = frame.view === "timer";
  const visiblePhase = runtimeState === "paused" && isClockView ? "已暂停" : runtimeState === "idle" && isClockView ? "等待开始" : frame.phase;

  return (
    <div className={`solution-wireframe-screen timer ${frame.mode ?? "focus"}`} data-prototype-surface={frame.surface} data-prototype-view={frame.view}>
      <header>
        <span className="wireframe-brand"><i />{productName}</span>
        <nav>{navigation.map((item) => <button data-prototype-control type="button" key={item} className={(item === "休息" ? frame.mode === "short-break" : item === "今日记录" ? frame.view === "summary" : item === "设置" ? frame.view === "setup" : frame.mode !== "short-break" && frame.view !== "summary" && frame.view !== "setup") ? "active" : ""} onClick={() => onNavigate(item)}>{item}</button>)}</nav>
      </header>
      <main>
        {frame.view !== "summary" && frame.view !== "notice" && <div className="wireframe-mode-tabs"><button data-prototype-control type="button" className={frame.mode === "focus" || frame.mode === "pause" ? "active" : ""} onClick={() => onNavigate(`${focusLabel}计时`)}>{focusLabel}</button><button data-prototype-control type="button" className={frame.mode === "short-break" ? "active" : ""} onClick={() => onNavigate("休息计时")}>休息</button></div>}
        {frame.view === "setup" ? (
          <div className="wireframe-settings" aria-label="时长设置">
            <label><span>专注时长</span><span><input aria-label="专注时长" type="number" defaultValue={frame.focusTimer === "待确认" ? undefined : Number(frame.focusTimer?.split(":")[0])} placeholder="待确认" />分钟</span></label>
            <label><span>休息时长</span><span><input aria-label="休息时长" type="number" defaultValue={frame.breakTimer === "待确认" ? undefined : Number(frame.breakTimer?.split(":")[0])} placeholder="待确认" />分钟</span></label>
          </div>
        ) : frame.view === "summary" ? (
          <div className="wireframe-summary"><small>今日完成</small><strong>0</strong><span>次完整{focusLabel}</span><p>{frame.description}</p></div>
        ) : frame.view === "notice" ? (
          <div className="wireframe-complete"><i aria-hidden="true">✓</i><strong>本轮{focusLabel}已完成</strong><span>{frame.completionMessage}</span><em><Bell size={14} />已触发应用内提醒</em></div>
        ) : (
          <div className="wireframe-clock">
            <small>{runtimeState === "paused" ? "计时已暂停" : runtimeState === "idle" ? "等待用户开始" : frame.mode === "focus" ? `保持${focusLabel}` : "休息阶段"}</small>
            <strong>{frame.timer}</strong>
            <span><i style={{ width: runtimeState === "idle" ? "0%" : runtimeState === "paused" ? "58%" : "24%" }} /></span>
            {frame.statusNote && <em className="wireframe-status-note"><Bell size={14} />{frame.statusNote}</em>}
          </div>
        )}
        {isClockView && (frame.supportsPause || frame.supportsReset || frame.supportsEarlyEnd) && <div className="wireframe-inline-controls" aria-label="计时控制">
          {frame.supportsPause && <button data-prototype-control type="button" onClick={() => setRuntimeState((state) => state === "running" ? "paused" : "running")}>{runtimeState === "paused" ? "继续" : runtimeState === "idle" ? "开始" : "暂停"}</button>}
          {frame.supportsReset && <button data-prototype-control type="button" onClick={() => { setRuntimeState("idle"); setConfirmingEarlyEnd(false); }}>重置</button>}
          {frame.supportsEarlyEnd && <button data-prototype-control type="button" onClick={() => setConfirmingEarlyEnd(true)}>提前结束</button>}
        </div>}
        {confirmingEarlyEnd && <div className="wireframe-confirm-end" role="alert"><span>{frame.confirmsEarlyEnd ? `确认提前结束？本轮不会计入完成次数。` : "提前结束后，本轮不会计入完成次数。"}</span><div><button data-prototype-control type="button" onClick={() => setConfirmingEarlyEnd(false)}>取消</button><button data-prototype-control type="button" onClick={() => { setRuntimeState("idle"); setConfirmingEarlyEnd(false); }}>确认结束</button></div></div>}
        <div className="wireframe-rounds"><span>当前状态 <strong>{visiblePhase}</strong></span><span>来源：完整 PRD</span></div>
        <div className="wireframe-actions">
          {frame.secondaryAction && <button data-prototype-control type="button" className="secondary" aria-label="次要操作" onClick={onAdvance}><RotateCcw size={15} />{frame.secondaryAction}</button>}
          <button data-prototype-control type="button" className="primary" onClick={onAdvance}>{frame.mode === "pause" ? <Pause size={16} /> : <Play size={16} />}{frame.action}</button>
        </div>
      </main>
    </div>
  );
}

function GenericWireframe({ frame, productName, onAdvance }: { frame: StoryFrame; productName: string; onAdvance: () => void }) {
  return (
    <div className="solution-wireframe-screen generic">
      <header><span className="wireframe-brand"><i />{productName}</span><nav><span className="active">当前流程</span></nav></header>
      <main>
        <span className="generic-wireframe-kicker">{frame.eyebrow}</span>
        <h3>{frame.title}</h3>
        <p>{frame.description}</p>
        <div className="generic-wireframe-grid"><button data-prototype-control type="button" aria-label="打开第一项" onClick={onAdvance} /><button data-prototype-control type="button" aria-label="打开第二项" onClick={onAdvance} /><button data-prototype-control type="button" aria-label="打开第三项" onClick={onAdvance} /></div>
        <button data-prototype-control type="button" className="primary" onClick={onAdvance}><MousePointerClick size={16} />{frame.action}</button>
      </main>
    </div>
  );
}

export function SolutionVisualDecisionView({ projectId, prdContent }: SolutionVisualDecisionViewProps) {
  const fullDocument = useMemo(() => recordOf(prdContent.full_document), [prdContent]);
  const hasFullDocument = Object.keys(fullDocument).length > 0;
  const documentTitle = typeof fullDocument.document_title === "string" ? fullDocument.document_title : "完整 PRD 待补齐";
  const productName = productNameFromFullDocument(fullDocument);
  const sourceText = JSON.stringify(fullDocument);
  const isTimer = hasFullDocument && /番茄|倒计时|计时器|专注.{0,8}休息|\d+\s*分钟专注/.test(sourceText);
  const prototypeContract = useMemo(() => buildLowFidelityPrototypeContract(prdContent), [prdContent]);
  const frames = useMemo(() => {
    if (!hasFullDocument) return [missingFullDocumentFrame()];
    const derived = framesFromFullDocument(fullDocument);
    return derived.length > 0 ? derived : [missingFullDocumentFrame()];
  }, [fullDocument, hasFullDocument]);
  const navigation = useMemo(() => {
    const items = ["计时"];
    if (frames.some((frame) => frame.surface === "timer-records" || frame.surface === "records")) items.push("今日记录");
    if (frames.some((frame) => frame.surface === "timer-setup" || frame.surface === "settings")) items.push("设置");
    return items;
  }, [frames]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [uiStyleKey, setUiStyleKey] = useState<UiStyleKey>(() => loadUiStylePreference(projectId) ?? "duolingo-sticker");
  const safeActiveIndex = Math.min(activeIndex, frames.length - 1);
  const active = frames[safeActiveIndex];

  function chooseUiStyle(value: UiStyleKey) {
    setUiStyleKey(value);
    saveUiStylePreference(projectId, value);
  }

  function goToFrame(index: number) {
    const safeIndex = (index + frames.length) % frames.length;
    setActiveIndex(safeIndex);
  }

  function goToSurface(surface: string | undefined, fallbackIndex = safeActiveIndex + 1) {
    const targetIndex = surface ? frames.findIndex((frame) => frame.surface === surface) : -1;
    goToFrame(targetIndex >= 0 ? targetIndex : fallbackIndex);
  }

  function goToIntent(intent: string) {
    const preferredSurfaces = /今日记录|历史|统计/.test(intent)
      ? ["timer-records", "records"]
      : /设置|偏好/.test(intent)
        ? ["timer-setup", "settings"]
        : /休息/.test(intent)
          ? ["timer-break"]
          : ["timer-focus", "browse-list"];
    const targetIndex = preferredSurfaces.map((surface) => frames.findIndex((frame) => frame.surface === surface)).find((index) => index >= 0);
    if (targetIndex !== undefined) goToFrame(targetIndex);
    else goToFrame(safeActiveIndex + 1);
  }

  function advancePrototype() {
    goToSurface(active.nextSurface);
  }

  return (
    <div className="solution-visual-view">
      <section className="solution-storyboard" aria-labelledby="solution-storyboard-title" data-prd-source="full_document" data-prototype-schema={prototypeContract.schema_version}>
        <header className="solution-storyboard-heading">
          <div>
            <span>可点击原型 · 根据你的需求生成</span>
            <h2 id="solution-storyboard-title">像真实用户一样，先把产品走一遍</h2>
            <p>点击原型中的按钮，按照真实使用顺序体验产品；相关功能会合并到同一界面中，完整需求仍会保留。</p>
          </div>
          <div className="storyboard-pager"><button type="button" onClick={() => goToFrame(safeActiveIndex - 1)} aria-label="上一个界面"><ArrowLeft size={16} /></button><span>{safeActiveIndex + 1} / {frames.length}</span><button type="button" onClick={() => goToFrame(safeActiveIndex + 1)} aria-label="下一个界面"><ArrowRight size={16} /></button></div>
        </header>

        <div className="solution-storyboard-stage">
          <div className="solution-browser-frame">
            <div className="solution-browser-bar"><span><i /><i /><i /></span><small>{documentTitle} · 低保真预览</small><em>可点击</em></div>
            {isTimer
              ? <TimerWireframe key={active.key} frame={active} productName={productName} navigation={navigation} onAdvance={advancePrototype} onNavigate={goToIntent} />
              : <GenericWireframe frame={active} productName={productName} onAdvance={advancePrototype} />}
          </div>

          <aside className="solution-frame-inspector">
            <div className="solution-frame-inspector-scroll">
              <span>用户会看到的第 {safeActiveIndex + 1} 个界面</span>
              <h3>{active.title}</h3>
              <p>{active.description}</p>
              <dl>
                <div><dt>这一步是否已经确定</dt><dd>{active.confirmation}</dd></div>
                <div><dt>点击“{active.action}”后会发生</dt><dd>{active.result}</dd></div>
                <div><dt>来自完整 PRD（整合 {active.sources.length} 条原始描述）</dt><dd>{active.sources.length > 1 ? <ol className="storyboard-source-list">{active.sources.map((item) => <li key={item}>{item}</li>)}</ol> : active.source}</dd></div>
                <div><dt>覆盖的功能（{active.requirements.length} 项）</dt><dd>{active.requirements.length > 0 ? <ul className="storyboard-requirement-list">{active.requirements.map((item) => <li key={item}>{item}</li>)}</ul> : "这一步已经直接包含在完整流程中。"}</dd></div>
              </dl>
            </div>
            <button type="button" onClick={advancePrototype}>体验下一界面<ArrowRight size={15} /></button>
          </aside>
        </div>

        <div className="solution-frame-strip" role="tablist" aria-label="完整 PRD 界面与交互">
          {frames.map((frame, index) => (
            <button key={frame.key} type="button" role="tab" aria-selected={index === safeActiveIndex} className={index === safeActiveIndex ? "active" : ""} onClick={() => setActiveIndex(index)}>
              <span className="mini-wireframe"><i /><i /><i /><b /></span>
              <small>界面 {index + 1} · 整合 {frame.sources.length} 条需求 · {frame.confirmation}</small><strong>{frame.title}</strong>
            </button>
          ))}
        </div>
      </section>

      <UiStylePicker value={uiStyleKey} onChange={chooseUiStyle} />
    </div>
  );
}
