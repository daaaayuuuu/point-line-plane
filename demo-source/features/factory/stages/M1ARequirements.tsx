"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, ArrowUp, BellRing, Bot, Check, ChevronRight, CircleCheckBig, CircleDollarSign, CircleHelp, Clock3, Coffee, Database, FileText, History, KeyRound, Lightbulb, LockKeyhole, MessageSquareText, Mic, MonitorSmartphone, PackageCheck, PencilLine, Plus, RefreshCw, Route, Search, ShieldAlert, Square, SquarePen, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { CODEX_EFFORTS, CODEX_MODEL_IDS, CODEX_REASONING_EFFORT_IDS } from "@/lib/codex-models";
import { api } from "@/lib/api/client";
import { clearRequirementRun, getRequirementRun, startRequirementRun } from "@/lib/requirement-runs";
import type { Artifact, CodexClarifyingQuestion, CodexConversationResponse, CodexConversationSummary, JsonObject } from "@/lib/api/types";
import { useCodexFastMode } from "@/lib/use-codex-fast-mode";
import { CodexModelSettings } from "../CodexModelSettings";
import type { StageProps } from "../StagePanels";
import { EmptyState, ObjectList, Panel, StageIntro, StatusPill, stringify } from "../StageUi";
import { SolutionVisualDecisionView } from "./SolutionVisualDecisionView";

type ConversationItem = {
  id: string;
  role: "assistant" | "user";
  text: string;
};

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
type GenerationPhase = "idle" | "thinking" | "writing" | "complete";

type OutputStream = {
  id: string;
  assistantMessageId: string;
  assistantText: string;
  draft: JsonObject;
  totalCharacters: number;
};

const PRD_STREAM_KEYS = [
  "title",
  "summary",
  "target_users",
  "problem",
  "core_flow",
  "features",
  "scope",
  "acceptance_criteria",
  "assumptions",
  "source_notes",
  "revision_notes",
] as const;

function countTextCharacters(value: unknown): number {
  if (typeof value === "string") return Array.from(value).length;
  if (Array.isArray(value)) return value.reduce((total, item) => total + countTextCharacters(item), 0);
  if (typeof value === "object" && value !== null) {
    return Object.values(value as Record<string, unknown>).reduce<number>((total, item) => total + countTextCharacters(item), 0);
  }
  return 0;
}

function prdCharacterCount(value: JsonObject): number {
  return PRD_STREAM_KEYS.reduce((total, key) => total + countTextCharacters(value[key]), 0);
}

function revealValue(value: unknown, budget: { remaining: number }): unknown {
  if (typeof value === "string") {
    if (budget.remaining <= 0) return undefined;
    const characters = Array.from(value);
    const visible = characters.slice(0, budget.remaining).join("");
    budget.remaining -= Math.min(characters.length, budget.remaining);
    return visible || undefined;
  }
  if (Array.isArray(value)) {
    const visibleItems: unknown[] = [];
    for (const item of value) {
      const visibleItem = revealValue(item, budget);
      if (visibleItem !== undefined) visibleItems.push(visibleItem);
      if (budget.remaining <= 0) break;
    }
    return visibleItems.length > 0 ? visibleItems : undefined;
  }
  if (typeof value === "object" && value !== null) {
    const visibleObject: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      const visibleItem = revealValue(item, budget);
      if (visibleItem !== undefined) visibleObject[key] = visibleItem;
      if (budget.remaining <= 0) break;
    }
    return Object.keys(visibleObject).length > 0 ? visibleObject : undefined;
  }
  return undefined;
}

function revealPrdContent(value: JsonObject, visibleCharacters: number): JsonObject {
  const budget = { remaining: visibleCharacters };
  const visible: JsonObject = {};
  for (const key of PRD_STREAM_KEYS) {
    const item = revealValue(value[key], budget);
    if (item !== undefined) visible[key] = item;
    if (budget.remaining <= 0) break;
  }
  return visible;
}

const PRD_PROGRESS_STEPS = [
  ["requirements", "整理已确认的产品需求"],
  ["tool", "调用 PRD 生成工具"],
  ["skill", "读取 PRD 生成规范"],
  ["writing", "生成完整产品需求文档"],
  ["validation", "校验文档结构与必填内容"],
  ["ready", "文档校验完成"],
] as const;

function PrdThinkingProgress({ phase, elapsedSeconds, reasoningSummary }: {
  phase: GenerationPhase; elapsedSeconds: number; reasoningSummary: string;
}) {
  // Only render known application events. Raw model reasoning is never shown.
  const reported = new Set([...reasoningSummary.matchAll(/^PRD_PROGRESS:(\w+)$/gm)].map((match) => match[1]));
  const steps = PRD_PROGRESS_STEPS.filter(([id]) => reported.has(id));
  const complete = reported.has("ready");
  if ((phase === "idle" || phase === "complete") && !complete) return null;
  return <section className={`prd-thinking-process is-${complete ? "complete" : phase}`} aria-label={steps.length ? "PRD 生成进度" : "回复进度"} aria-live="polite">
    <header><strong>{steps.length ? (complete ? "PRD 已生成" : "正在生成 PRD") : "正在处理你的消息"}</strong><span>{elapsedSeconds} 秒</span></header>
    {steps.length > 0 && <ol>{steps.map(([id, label], index) => {
      const done = complete || index < steps.length - 1;
      return <li key={id} className={done ? "completed" : "active"}>
        <span aria-hidden="true">{done ? <Check size={12} /> : <i />}</span>
        <p>{label}<span className="sr-only">{done ? "，已完成" : "，进行中"}</span></p>
      </li>;
    })}</ol>}
  </section>;
}

function CodexChoiceQuestion({
  question,
  selected,
  supplement,
  disabled,
  onToggle,
  onSupplementChange,
  onSubmit,
}: {
  question: CodexClarifyingQuestion;
  selected: string[];
  supplement: string;
  disabled: boolean;
  onToggle: (option: string) => void;
  onSupplementChange: (value: string) => void;
  onSubmit: () => void;
}) {
  const multiple = question.mode === "multiple";
  const supplementSelected = selected.some((option) => option.includes("其他"));
  const cardRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const scroll = cardRef.current?.closest(".codex-conversation-scroll");
      if (scroll) scroll.scrollTop = scroll.scrollHeight;
    });
    return () => cancelAnimationFrame(frame);
  }, [question, supplementSelected, supplement]);
  return (
    <section ref={cardRef} className="codex-choice-question" aria-label={question.prompt}>
      <div className="codex-choice-heading">
        <strong>{multiple ? "可多选" : "请选择一项"}</strong>
        <span>{multiple ? "选择所有符合的选项" : "选择最符合的一项"}</span>
      </div>
      <div className="codex-choice-options" role={multiple ? "group" : "radiogroup"} aria-label={question.prompt}>
        {question.options.map((option) => {
          const checked = selected.includes(option);
          return (
            <button
              key={option}
              type="button"
              className={checked ? "selected" : ""}
              role={multiple ? "checkbox" : "radio"}
              aria-checked={checked}
              disabled={disabled}
              onClick={() => onToggle(option)}
            >
              <span aria-hidden="true">{checked && <Check size={13} strokeWidth={3} />}</span>
              <b>{option}</b>
            </button>
          );
        })}
      </div>
      {supplementSelected && (
        <label className="codex-choice-supplement">
          <span>补充说明</span>
          <textarea
            value={supplement}
            disabled={disabled}
            maxLength={1000}
            placeholder="请输入你的具体需求"
            onChange={(event) => onSupplementChange(event.target.value)}
          />
        </label>
      )}
      <button
        className="codex-choice-submit"
        type="button"
        disabled={disabled || selected.length === 0 || (supplementSelected && !supplement.trim())}
        onClick={onSubmit}
      >确认选择</button>
    </section>
  );
}

function CodexMark() {
  return (
    <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor" fillRule="evenodd" aria-hidden="true">
      <path d="M9.205 8.658v-2.26c0-.19.072-.333.238-.428l4.543-2.616c.619-.357 1.356-.523 2.117-.523 2.854 0 4.662 2.212 4.662 4.566 0 .167 0 .357-.024.547l-4.71-2.759a.797.797 0 0 0-.856 0l-5.97 3.473Zm10.609 8.8V12.06c0-.333-.143-.57-.429-.737l-5.97-3.473 1.95-1.118a.433.433 0 0 1 .476 0l4.543 2.617c1.309.76 2.189 2.378 2.189 3.948 0 1.808-1.07 3.473-2.76 4.163ZM7.802 12.703l-1.95-1.142c-.167-.095-.239-.238-.239-.428V5.899c0-2.545 1.95-4.472 4.591-4.472 1 0 1.927.333 2.712.928L8.23 5.067c-.285.166-.428.404-.428.737v6.898ZM12 15.128l-2.795-1.57v-3.33L12 8.658l2.795 1.57v3.33L12 15.128Zm1.796 7.23c-1 0-1.927-.332-2.712-.927l4.686-2.712c.285-.166.428-.404.428-.737v-6.898l1.974 1.142c.167.095.238.238.238.428v5.233c0 2.545-1.974 4.472-4.614 4.472Zm-5.637-5.303-4.544-2.617c-1.308-.761-2.188-2.378-2.188-3.948A4.482 4.482 0 0 1 4.21 6.327v5.423c0 .333.143.571.428.738l5.947 3.449-1.95 1.118a.432.432 0 0 1-.476 0Zm-.262 3.9c-2.688 0-4.662-2.021-4.662-4.519 0-.19.024-.38.047-.57l4.686 2.71c.286.167.571.167.856 0l5.97-3.448v2.26c0 .19-.07.333-.237.428l-4.543 2.616c-.619.357-1.356.523-2.117.523Zm5.899 2.83a5.947 5.947 0 0 0 5.827-4.756C22.287 18.339 24 15.84 24 13.296c0-1.665-.713-3.282-1.998-4.448.119-.5.19-.999.19-1.498 0-3.401-2.759-5.947-5.946-5.947-.642 0-1.26.095-1.88.31A5.962 5.962 0 0 0 10.205 0a5.947 5.947 0 0 0-5.827 4.757C1.713 5.447 0 7.945 0 10.49c0 1.666.713 3.283 1.998 4.448-.119.5-.19 1-.19 1.499 0 3.401 2.759 5.946 5.946 5.946.642 0 1.26-.095 1.88-.309a5.96 5.96 0 0 0 4.162 1.713Z" />
    </svg>
  );
}

function solutionRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function solutionLines(value: unknown): string[] {
  const values = Array.isArray(value) ? value : value === null || value === undefined || value === "" ? [] : [value];
  return values.map((item) => stringify(item).trim()).filter(Boolean);
}

function uniqueSolutionLines(...values: unknown[]): string[] {
  return [...new Set(values.flatMap((value) => solutionLines(value)))];
}

function friendlySolutionText(value: string): string {
  return value
    .replaceAll("响应式网页", "电脑和手机都能使用的网页")
    .replaceAll("当前浏览器数据保存", "数据保存在当前设备的浏览器里")
    .replaceAll("浏览器本地数据保存", "数据保存在当前设备的浏览器里")
    .replaceAll("浏览器本地", "当前浏览器")
    .replaceAll("原生移动端应用", "需要安装的手机 App")
    .replaceAll("本地 M1", "当前制作与预览阶段")
    .replaceAll("M1", "首版")
    .replaceAll("mock", "体验环境")
    .replaceAll("Key", "服务授权")
    .replaceAll("Token", "使用额度")
    .replaceAll("API", "服务连接")
    .replaceAll("冒烟", "真实效果检查")
    .replaceAll("公网托管", "正式发布上线");
}

function friendlyAccount(value: string): string {
  if (/mock|真实模型|Key|供应商/.test(value)) return "现在无需准备其他账号；只有后续确实启用真实 AI 服务时，才会在发布前请你完成授权。";
  return friendlySolutionText(value);
}

function friendlyRisk(value: string): string {
  if (value.includes("任意代码沙箱")) return "工厂只会生成已确认范围内的产品功能，不会执行方案之外的任意操作。";
  if (value.includes("本地预览不等于公网托管")) return "当前先提供本地预览；需要让其他人访问时，会在第 4 步单独确认并发布上线。";
  if (/模型效果|真实 Key|冒烟/.test(value)) return "如果后续加入真实 AI 功能，上线前还会进行一次真实效果检查，未验证前不会宣称已经可用。";
  return friendlySolutionText(value);
}

function friendlyDeliverable(value: string): string {
  if (value.includes("版本化 PRD")) return "可以继续修改、可以追溯版本的产品需求文档";
  if (value === "推荐方案") return "这份已经确认的产品方案";
  if (value.includes("持久化开发任务")) return "可暂停、可恢复的产品生成记录";
  if (/绑定代码版本.*预览/.test(value)) return "与保存版本对应、可以亲手操作的产品预览";
  return friendlySolutionText(value);
}

function solutionCostItems(value: unknown): Array<{ title: string; amount: string; note: string }> {
  if (!Array.isArray(value)) return [];
  return value.map((item, index) => {
    const record = solutionRecord(item);
    const title = String(record.item ?? `费用项 ${index + 1}`);
    if (/本地|M1/.test(title)) return { title: "制作和预览", amount: "当前阶段不增加云服务费用", note: "先在本机生成并体验；正式发布前再确认上线成本。" };
    if (/模型|AI/.test(title)) return { title: "AI 服务（需要时）", amount: "按实际使用量计费", note: "启用前会展示预计费用，并再次请你确认。" };
    return {
      title: friendlySolutionText(title),
      amount: friendlySolutionText(String(record.estimate ?? "待确认")),
      note: friendlySolutionText(String(record.note ?? "费用发生前会再次确认。")),
    };
  });
}

function SolutionFact({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return <article><span><Icon size={17} /></span><div><small>{label}</small><strong>{value}</strong></div></article>;
}

export function SolutionDecisionView({ content, prdContent, prdTitle }: { content: Record<string, unknown>; prdContent: Record<string, unknown>; prdTitle: string }) {
  const prdScope = solutionRecord(prdContent.scope);
  const userFlow = uniqueSolutionLines(prdContent.core_flow);
  const features = uniqueSolutionLines(prdContent.features);
  const included = uniqueSolutionLines(content.product_scope, prdScope.included).map(friendlySolutionText);
  const deferred = uniqueSolutionLines(content.deferred, prdScope.excluded).map(friendlySolutionText);
  const assumptions = uniqueSolutionLines(prdContent.assumptions);
  const dataNotes = uniqueSolutionLines(included, assumptions)
    .filter((line) => /数据|保存|浏览器|记录|同步|备份|账号|隐私|文件|日期/.test(line))
    .map(friendlySolutionText)
    .slice(0, 4);
  const aiItems = uniqueSolutionLines(userFlow, features).filter((line) => /\bAI\b|Agent|智能|模型|识别|分析|生成|总结|推荐|问答|对话/.test(line));
  const accounts = uniqueSolutionLines(content.external_accounts).map(friendlyAccount);
  const risks = uniqueSolutionLines(content.risks).map(friendlyRisk);
  const deliverables = uniqueSolutionLines(content.deliverables).map(friendlyDeliverable);
  const costs = solutionCostItems(content.user_costs);
  const technical = Object.fromEntries(["architecture", "technical_contract"].filter((key) => content[key] !== undefined).map((key) => [key, content[key]]));
  const surface = included.find((item) => /网页|App|小程序|桌面/.test(item)) ?? "一个可以直接操作的网页首版";
  const dataSummary = dataNotes.find((line) => /浏览器|设备|云端|本地|同步|备份/.test(line))
    ?? dataNotes[0]
    ?? "只保存完成核心任务所需的数据，发布前会再说明保存位置和删除方式。";
  const accountSummary = accounts[0] ?? "当前不需要额外账号或授权。";
  const costSummary = costs[0]?.amount ?? "发生费用前会再次请你确认。";
  const flow = userFlow.length > 0 ? userFlow : ["用户进入产品", "完成核心操作", "查看并保存结果"];
  const featureItems = features.length > 0 ? features : included;
  const aiSummary = aiItems.length > 0
    ? `AI 会参与：${aiItems.slice(0, 3).join("；")}。信息不足或处理失败时，页面会明确提示，不会假装完成。`
    : "首版核心功能不依赖 AI。用户使用产品时不会调用模型，因此运行更稳定，也不会产生模型使用费；AI 只在工厂里帮助生成和检查产品。";

  return (
    <div className="solution-decision-view solution-whitebox-view">
      <div className="solution-requirement-baseline"><Check size={17} /><div><small>产品目标已确认</small><strong>{prdTitle}</strong><p>下面只展示会影响用户体验、费用、数据和交付结果的内容，具体技术由工厂处理。</p></div></div>

      <section className="solution-recommendation-card" aria-label="工厂推荐方案">
        <span className="solution-recommendation-label"><Lightbulb size={15} />工厂推荐</span>
        <h2>先做一个能完整跑通核心任务的首版</h2>
        <p>{String(prdContent.summary ?? "先让用户顺利完成最重要的任务，再根据真实体验继续增加功能。")}</p>
        <div className="solution-why"><strong>为什么推荐这样做</strong><span>最快拿到真实预览，当前成本最低，后续仍可以继续扩展。</span></div>
        <div className="solution-next-step-hint"><ArrowRight size={15} /><span>看完后，在页面底部点击“方案没问题，开始生成产品”即可进入下一步。</span></div>
        <div className="solution-fact-grid">
          <SolutionFact icon={MonitorSmartphone} label="用户怎么使用" value={surface} />
          <SolutionFact icon={Database} label="数据放在哪里" value={dataSummary} />
          <SolutionFact icon={KeyRound} label="现在要准备什么" value={accountSummary} />
          <SolutionFact icon={CircleDollarSign} label="当前费用" value={costSummary} />
        </div>
      </section>

      <section className="solution-whitebox-section" aria-labelledby="solution-flow-title">
        <header><span><Route size={18} /></span><div><small>从打开产品到完成目标</small><h3 id="solution-flow-title">用户会怎样完成目标</h3></div></header>
        <ol className="solution-user-flow">{flow.map((item, index) => <li key={`solution-flow-${index}`}><span>{index + 1}</span><p>{friendlySolutionText(item)}</p></li>)}</ol>
      </section>

      <div className="solution-scope-overview">
        <section className="solution-scope-card included" aria-labelledby="solution-included-title">
          <header><CircleCheckBig size={18} /><h3 id="solution-included-title">首版包含什么</h3></header>
          <p>这些能力会进入第一版，并在预览中逐项检查。</p>
          <ul>{included.map((item, index) => <li key={`solution-included-${index}`}><Check size={14} />{item}</li>)}</ul>
        </section>
        <section className="solution-scope-card deferred" aria-labelledby="solution-deferred-title">
          <header><PackageCheck size={18} /><h3 id="solution-deferred-title">这批功能以后再决定</h3></header>
          <p>暂时不做不代表永远不做，先避免首版过重。</p>
          <ul>{deferred.map((item, index) => <li key={`solution-deferred-${index}`}>{item}</li>)}</ul>
        </section>
      </div>

      <section className="solution-whitebox-section" aria-labelledby="solution-features-title">
        <header><span><MonitorSmartphone size={18} /></span><div><small>用户真正能看到和操作的部分</small><h3 id="solution-features-title">首版页面与功能</h3></div></header>
        <div className="solution-feature-list">{featureItems.map((item, index) => <div key={`solution-feature-${index}`}><span>{index + 1}</span><p>{friendlySolutionText(item)}</p></div>)}</div>
      </section>

      <div className="solution-insight-grid">
        <section className="solution-insight-card"><header><span><Bot size={18} /></span><div><small>是否依赖模型</small><h3>AI 在产品里做什么</h3></div></header><p>{aiSummary}</p></section>
        <section className="solution-insight-card"><header><span><Database size={18} /></span><div><small>保存什么、能否恢复</small><h3>数据怎么保存</h3></div></header><ul>{(dataNotes.length > 0 ? dataNotes : [dataSummary]).map((item, index) => <li key={`solution-data-${index}`}>{item}</li>)}</ul></section>
        <section className="solution-insight-card"><header><span><CircleDollarSign size={18} /></span><div><small>什么时候才会收费</small><h3>费用怎么算</h3></div></header><div className="solution-cost-list">{(costs.length > 0 ? costs : [{ title: "当前方案", amount: costSummary, note: "产生费用前会再次确认。" }]).map((item) => <div key={item.title}><strong>{item.title}</strong><span>{item.amount}</span><small>{item.note}</small></div>)}</div></section>
        <section className="solution-insight-card"><header><span><KeyRound size={18} /></span><div><small>现在需要你提供什么</small><h3>需要什么账号或授权</h3></div></header><ul>{(accounts.length > 0 ? accounts : [accountSummary]).map((item, index) => <li key={`solution-account-${index}`}>{item}</li>)}</ul></section>
        <section className="solution-insight-card"><header><span><ShieldAlert size={18} /></span><div><small>提前知道，避免误解</small><h3>你需要提前知道的限制</h3></div></header><ul>{(risks.length > 0 ? risks : ["当前没有需要额外确认的高风险事项。"]).map((item, index) => <li key={`solution-risk-${index}`}>{item}</li>)}</ul></section>
        <section className="solution-insight-card"><header><span><PackageCheck size={18} /></span><div><small>完成这一轮后</small><h3>你最终会拿到什么</h3></div></header><ul>{(deliverables.length > 0 ? deliverables : ["可以亲手操作的产品预览", "产品说明和质量检查结果"]).map((item, index) => <li key={`solution-delivery-${index}`}>{item}</li>)}</ul></section>
      </div>

      <section className="solution-safeguard-section" aria-labelledby="solution-safeguards-title">
        <header><small>把后端技术翻译成你能判断的结果</small><h3 id="solution-safeguards-title">工厂在背后怎样保障</h3></header>
        <div className="solution-safeguard-grid">
          <article><span><Database size={17} /></span><strong>重要内容会保存</strong><p>当前进度和每次确认都会留下记录，刷新后仍能恢复。</p></article>
          <article><span><RefreshCw size={17} /></span><strong>中断后可以继续</strong><p>生成时间较长时会保存进度，失败后从最近一步继续。</p></article>
          <article><span><CircleHelp size={17} /></span><strong>出错会告诉你怎么办</strong><p>页面说明发生了什么、有什么影响和下一步怎么做。</p></article>
          <article><span><LockKeyhole size={17} /></span><strong>授权信息不会暴露</strong><p>账号和服务授权只交给后台使用，不写进页面和交付代码。</p></article>
        </div>
      </section>

      {Object.keys(technical).length > 0 && <ObjectList value={technical} />}
    </div>
  );
}

const GENERIC_PRD_PREVIEW = {
  title: "番茄时间闹钟",
  summary: "用番茄工作法安排专注与休息节奏，通过清晰的倒计时和提醒帮助用户保持专注。",
  target_users: ["希望减少分心、提高工作效率的职场人", "需要规律学习和休息节奏的学生"],
  problem: "长时间工作或学习时容易分心、拖延或忘记休息，缺少一个简单、可持续的时间管理节奏。",
  core_flow: [
    "用户设定专注时长和休息时长",
    "点击开始，进入专注倒计时",
    "倒计时结束后播放声音并弹出提醒",
    "用户进入短休息或跳过休息",
    "完成一轮后记录专注次数并开始下一轮",
  ],
  features: [
    "25 分钟专注与 5 分钟休息默认方案",
    "专注、短休息和长休息模式切换",
    "开始、暂停、继续和重置倒计时",
    "到时声音与桌面通知提醒",
    "当日完成番茄数统计",
  ],
  scope: {
    included: ["网页端倒计时", "专注与休息模式", "时长自定义", "本地保存当日专注记录"],
    excluded: ["跨设备账号同步", "团队专注排行榜", "任务管理和日历集成"],
  },
  acceptance_criteria: [
    "用户可以启动、暂停、继续和重置倒计时",
    "专注结束后自动进入休息提醒状态",
    "计时过程中刷新页面不会丢失当前进度",
    "每完成一次专注后，当日番茄数正确增加",
  ],
  assumptions: ["首版以电脑浏览器使用为主", "用户允许浏览器播放提示音和发送通知", "专注记录仅保存在当前设备"],
  source_notes: ["通用产品示例，用于展示 PRD 的固定结构", "开始对话后将由用户的真实需求逐项替换"],
  revision_notes: ["用户提出调整意见后，在这里记录版本变化"],
} satisfies JsonObject;

function withoutTerminalPeriods(value: string): string {
  return value.trimEnd().replace(/[。.]+$/g, "");
}

function prdItems(value: unknown, fallback = "待确认"): string[] {
  const items = Array.isArray(value) ? value.map((item) => stringify(item)) : value === null || value === undefined || value === "" ? [] : [stringify(value)];
  const visibleItems = items.filter((item) => item.trim());
  return visibleItems.length > 0 ? visibleItems.map(withoutTerminalPeriods) : fallback ? [withoutTerminalPeriods(fallback)] : [];
}

function PrdSectionHeading({ icon, title }: { icon: "computer" | "checkbox" | "live-notice"; title: string }) {
  return <header className="prd-section-heading"><span className={`prd-section-heading-icon is-${icon}`} aria-hidden="true" /><h3>{title}</h3></header>;
}

function DoubleRingTargetIcon() {
  return (
    <svg className="prd-double-ring-icon" width="18" height="18" viewBox="0 0 18 18" fill="none" data-rings="2" aria-hidden="true">
      <circle cx="9" cy="9" r="7" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="9" cy="9" r="3" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function PrdStructuredContent({ value, placeholder = false, streaming = false }: { value: Record<string, unknown>; placeholder?: boolean; streaming?: boolean }) {
  const scope = typeof value.scope === "object" && value.scope !== null && !Array.isArray(value.scope)
    ? value.scope as Record<string, unknown>
    : {};
  const fallback = streaming ? "" : "待确认";
  const targetUsers = prdItems(value.target_users, fallback);
  const problems = prdItems(value.problem, fallback);
  const coreFlow = prdItems(value.core_flow, fallback);
  const features = prdItems(value.features, fallback);
  const included = prdItems(scope.included, fallback);
  const excluded = prdItems(scope.excluded, fallback);
  const acceptance = prdItems(value.acceptance_criteria, fallback);
  const assumptions = prdItems(value.assumptions, fallback);
  const sources = prdItems(value.source_notes, fallback);
  const revisions = prdItems(value.revision_notes, streaming ? "" : "暂无修改记录");

  return (
    <div className={`prd-structured-content${placeholder ? " is-placeholder" : ""}`}>
      <section className="prd-definition-rail" aria-label="用户与问题">
        <article className="prd-insight-card audience">
          <header><DoubleRingTargetIcon /><strong>目标用户</strong></header>
          <ul>{targetUsers.map((item, index) => <li key={`user-${index}`}>{item}</li>)}</ul>
        </article>
        <article className="prd-insight-card problem">
          <header><CircleHelp size={18} /><strong>核心问题</strong></header>
          <ul>{problems.map((item, index) => <li key={`problem-${index}`}>{item}</li>)}</ul>
        </article>
      </section>

      <section className="prd-structured-section prd-plan-section" aria-label="产品方案">
        <PrdSectionHeading icon="computer" title="产品方案" />
        <div className="prd-plan-panel">
          <article className="prd-plan-step">
            <header><span>1</span><strong>核心使用流程</strong></header>
            <ol className="prd-flow-list">{coreFlow.map((item, index) => <li key={`flow-${index}`}>{item}</li>)}</ol>
          </article>
          <article className="prd-plan-step">
            <header><span>2</span><strong>主要功能</strong></header>
            <ul className="prd-feature-list">{features.map((item, index) => <li key={`feature-${index}`}>{item}</li>)}</ul>
          </article>
          <article className="prd-plan-step">
            <header><span>3</span><strong>首版范围</strong></header>
            <div className="prd-scope-grid">
              <div className="included"><strong>本期包含</strong><ul>{included.map((item, index) => <li key={`included-${index}`}>{item}</li>)}</ul></div>
              <div className="excluded"><strong>暂不包含</strong><ul>{excluded.map((item, index) => <li key={`excluded-${index}`}>{item}</li>)}</ul></div>
            </div>
          </article>
        </div>
      </section>

      <section className="prd-structured-section" aria-label="完成标准">
        <PrdSectionHeading icon="checkbox" title="完成标准" />
        <ol className="prd-acceptance-list">{acceptance.map((item, index) => <li key={`acceptance-${index}`}><strong>标准 {index + 1}</strong><p>{item}</p></li>)}</ol>
      </section>

      <section className="prd-structured-section prd-notes-section" aria-label="补充说明">
        <PrdSectionHeading icon="live-notice" title="补充说明" />
        <div className="prd-notes-grid">
          <article className="assumptions"><strong>当前假设</strong><ul>{assumptions.map((item, index) => <li key={`assumption-${index}`}>{item}</li>)}</ul></article>
          <article className="sources"><strong>需求来源</strong><ul>{sources.map((item, index) => <li key={`source-${index}`}>{item}</li>)}</ul></article>
          <article className="revisions"><strong>修改记录</strong><ul>{revisions.map((item, index) => <li key={`revision-${index}`}>{item}</li>)}</ul></article>
        </div>
      </section>
    </div>
  );
}

function FullPrdDocument({ artifact }: { artifact: Artifact }) {
  const full = typeof artifact.content.full_document === "object" && artifact.content.full_document !== null && !Array.isArray(artifact.content.full_document)
    ? artifact.content.full_document as Record<string, unknown>
    : {};
  const documentTitle = String(full.document_title ?? "待确认");
  const documentSummary = String(full.document_summary ?? "待确认");
  const productType = full.product_type === "agent" ? "agent" : "standard";
  const generationSkill = typeof full.generation_skill === "object" && full.generation_skill !== null && !Array.isArray(full.generation_skill)
    ? full.generation_skill as Record<string, unknown>
    : {};
  const skillLabel = generationSkill.name === "ai-pm-prd" ? "ai-pm-prd" : "历史生成规则（未记录）";
  const usageContext = prdItems(full.usage_context);
  const inputs = prdItems(full.inputs);
  const endToEndLoop = prdItems(full.end_to_end_loop);
  const deliverables = prdItems(full.deliverables);
  const functionalRequirements = prdItems(full.functional_requirements);
  const nonFunctionalRequirements = prdItems(full.non_functional_requirements);
  const includedScope = prdItems(full.in_scope);
  const excludedScope = prdItems(full.out_of_scope);
  const externalActions = prdItems(full.external_actions);
  const domainKnowledge = prdItems(full.domain_knowledge);
  const dataAndState = prdItems(full.data_and_state);
  const boundaries = prdItems(full.boundaries);
  const constraints = prdItems(full.constraints);
  const openQuestions = prdItems(full.open_questions);
  const traceability = prdItems(full.traceability);
  const revisions = prdItems(full.revision_history, "暂无修改记录");
  const failureStrategies = Array.isArray(full.failure_strategies)
    ? full.failure_strategies.map((item) => typeof item === "object" && item !== null ? item as Record<string, unknown> : {})
    : [];
  const successMetrics = Array.isArray(full.success_metrics)
    ? full.success_metrics.map((item) => typeof item === "object" && item !== null ? item as Record<string, unknown> : {})
    : [];
  const harness = typeof full.harness === "object" && full.harness !== null && !Array.isArray(full.harness)
    ? full.harness as Record<string, unknown>
    : {};
  const harnessSections = [
    ["tools", "所需外部能力"],
    ["knowledge", "领域知识要求"],
    ["observation", "结果验证信号"],
    ["actions", "系统动作"],
    ["permissions", "权限要求"],
  ] as const;
  const blueprint = typeof full.blueprint_process === "object" && full.blueprint_process !== null && !Array.isArray(full.blueprint_process)
    ? full.blueprint_process as Record<string, unknown>
    : null;
  const componentSelection = blueprint && Array.isArray(blueprint.component_selection)
    ? blueprint.component_selection.map((item) => typeof item === "object" && item !== null ? item as Record<string, unknown> : {})
    : [];
  const architectureLayers = blueprint && Array.isArray(blueprint.layered_architecture)
    ? blueprint.layered_architecture.map((item) => typeof item === "object" && item !== null ? item as Record<string, unknown> : {})
    : [];
  const toolCatalog = blueprint && Array.isArray(blueprint.tool_catalog)
    ? blueprint.tool_catalog.map((item) => typeof item === "object" && item !== null ? item as Record<string, unknown> : {})
    : [];
  const codePlan = blueprint && typeof blueprint.code_generation_plan === "object" && blueprint.code_generation_plan !== null && !Array.isArray(blueprint.code_generation_plan)
    ? blueprint.code_generation_plan as Record<string, unknown>
    : {};

  return (
    <article className="prd-full-document" aria-label={`完整 PRD 第 ${artifact.version} 版`}>
      <header className="prd-full-document-title">
        <span>产品需求文档 · 第 {artifact.version} 版 · {productType === "agent" ? "Agent 产品" : "通用产品"}</span>
        <h3>{documentTitle}</h3>
        <p>{withoutTerminalPeriods(documentSummary)}</p>
        <small className="prd-full-skill-source">生成规范：{skillLabel}</small>
      </header>

      <section data-prd-section="goals">
        <h4><span>01</span>产品目标与成功标准</h4>
        <div className="prd-full-document-grid">
          <div><strong>产品目标</strong><p>{withoutTerminalPeriods(String(full.product_goal ?? "待确认"))}</p></div>
          <div><strong>怎样算做成</strong><p>{withoutTerminalPeriods(String(full.success_definition ?? "待确认"))}</p></div>
        </div>
      </section>

      <section data-prd-section="users">
        <h4><span>02</span>用户与使用方式</h4>
        <div className="prd-full-document-grid">
          <div><strong>用户与使用场景</strong><ul>{usageContext.map((item, index) => <li key={`full-context-${index}`}>{item}</li>)}</ul></div>
          <div><strong>交互方式</strong><p>{withoutTerminalPeriods(String(full.interaction_model ?? "待确认"))}</p></div>
          <div><strong>用户输入</strong><ul>{inputs.map((item, index) => <li key={`full-input-${index}`}>{item}</li>)}</ul></div>
          <div><strong>产品交付结果</strong><ul>{deliverables.map((item, index) => <li key={`full-deliverable-${index}`}>{item}</li>)}</ul></div>
        </div>
      </section>

      <section data-prd-section="core-flow">
        <h4><span>03</span>核心业务流程</h4>
        <ol className="prd-full-loop">{endToEndLoop.map((item, index) => <li key={`full-loop-${index}`}>{item}</li>)}</ol>
      </section>

      <section data-prd-section="requirements">
        <h4><span>04</span>功能与质量要求</h4>
        <div className="prd-full-document-grid">
          <div><strong>功能需求</strong><ul>{functionalRequirements.map((item, index) => <li key={`full-functional-${index}`}>{item}</li>)}</ul></div>
          <div><strong>非功能需求</strong><ul>{nonFunctionalRequirements.map((item, index) => <li key={`full-nonfunctional-${index}`}>{item}</li>)}</ul></div>
          <div><strong>首版包含</strong><ul>{includedScope.map((item, index) => <li key={`full-included-${index}`}>{item}</li>)}</ul></div>
          <div><strong>暂不包含</strong><ul>{excludedScope.map((item, index) => <li key={`full-excluded-${index}`}>{item}</li>)}</ul></div>
        </div>
      </section>

      <section data-prd-section="dependencies">
        <h4><span>05</span>数据与外部依赖</h4>
        <div className="prd-full-document-grid">
          <div><strong>外部动作与系统</strong><ul>{externalActions.map((item, index) => <li key={`full-action-${index}`}>{item}</li>)}</ul></div>
          <div><strong>领域知识</strong><ul>{domainKnowledge.map((item, index) => <li key={`full-knowledge-${index}`}>{item}</li>)}</ul></div>
          <div><strong>数据与状态</strong><ul>{dataAndState.map((item, index) => <li key={`full-data-${index}`}>{item}</li>)}</ul></div>
        </div>
      </section>

      <section data-prd-section="capabilities">
        <h4><span>06</span>实现约束与能力需求</h4>
        <div className="prd-full-harness">
          {harnessSections.map(([key, label]) => <div key={key}><strong>{label}</strong><ul>{prdItems(harness[key]).map((item, index) => <li key={`full-${key}-${index}`}>{item}</li>)}</ul></div>)}
        </div>
      </section>

      <section data-prd-section="boundaries">
        <h4><span>07</span>产品边界与异常处理</h4>
        <div className="prd-full-document-grid">
          <div><strong>明确不能做</strong><ul>{boundaries.map((item, index) => <li key={`full-boundary-${index}`}>{item}</li>)}</ul></div>
          <div><strong>约束条件</strong><ul>{constraints.map((item, index) => <li key={`full-constraint-${index}`}>{item}</li>)}</ul></div>
        </div>
        <div className="prd-full-table">
          {failureStrategies.length > 0 ? failureStrategies.map((item, index) => <div key={`full-failure-${index}`}><strong>{String(item.scenario ?? "待确认")}</strong><p>{String(item.fallback ?? "待确认")}</p></div>) : <div><strong>待确认</strong><p>待确认</p></div>}
        </div>
      </section>

      <section data-prd-section="metrics">
        <h4><span>08</span>验收与成功指标</h4>
        <div className="prd-full-metrics">
          {successMetrics.length > 0 ? successMetrics.map((item, index) => <div key={`full-metric-${index}`}><strong>{String(item.metric ?? `指标 ${index + 1}`)}</strong><p>{String(item.target ?? "待确认")}</p><small>{String(item.measurement ?? "待确认")}</small></div>) : <div><strong>核心目标达成率</strong><p>待确认</p><small>待确认</small></div>}
        </div>
      </section>

      <section data-prd-section="traceability">
        <h4><span>09</span>待确认事项与需求追溯</h4>
        <div className="prd-full-document-grid">
          <div><strong>待确认事项</strong><ul>{openQuestions.map((item, index) => <li key={`full-question-${index}`}>{item}</li>)}</ul></div>
          <div><strong>需求来源</strong><ul>{traceability.map((item, index) => <li key={`full-trace-${index}`}>{item}</li>)}</ul></div>
          <div><strong>修改记录</strong><ul>{revisions.map((item, index) => <li key={`full-revision-${index}`}>{item}</li>)}</ul></div>
        </div>
      </section>

      {productType === "agent" && blueprint && (
        <section data-prd-section="agent-architecture" className="prd-full-agent-architecture">
          <h4><span>10</span>Agent Harness 与技术架构</h4>
          <p className="prd-full-agent-note">该部分仅在需求证据表明产品属于 Agent 时生成，并遵循最小组件原则。</p>

          <h5>组件选型与取舍</h5>
          <div className="prd-full-component-list">
            {componentSelection.map((item, index) => (
              <article key={`full-component-${index}`} data-decision={String(item.decision ?? "pending")}>
                <header><strong>{String(item.component ?? `组件 ${index + 1}`)}</strong><span>{String(item.decision ?? "pending")}</span></header>
                <p>{String(item.reason ?? "待确认")}</p>
                <small>{String(item.production_notes ?? "待确认")} · {String(item.reference ?? "待确认")}</small>
              </article>
            ))}
          </div>

          <h5>标准七层架构</h5>
          <div className="prd-full-layer-list">
            {architectureLayers.map((item, index) => (
              <article key={`full-layer-${index}`}>
                <span>{String(item.layer ?? index + 1).padStart(2, "0")}</span>
                <div><strong>{String(item.name ?? "待确认")}</strong><ul>{prdItems(item.responsibilities).map((line, lineIndex) => <li key={`full-layer-${index}-${lineIndex}`}>{line}</li>)}</ul></div>
                <div><small>落地锚点</small><ul>{prdItems(item.implementation_anchors).map((line, lineIndex) => <li key={`full-anchor-${index}-${lineIndex}`}>{line}</li>)}</ul></div>
              </article>
            ))}
          </div>

          <div className="prd-full-document-grid prd-full-agent-grid">
            <div><strong>跨层主数据流</strong><ol>{prdItems(blueprint.cross_layer_data_flow).map((item, index) => <li key={`full-data-flow-${index}`}>{item}</li>)}</ol></div>
            <div><strong>上下文与记忆</strong><ul>{prdItems(blueprint.context_and_memory_strategy).map((item, index) => <li key={`full-memory-${index}`}>{item}</li>)}</ul></div>
            <div><strong>安全与权限</strong><ul>{prdItems(blueprint.security_and_permissions).map((item, index) => <li key={`full-security-${index}`}>{item}</li>)}</ul></div>
            <div><strong>可观测性</strong><ul>{prdItems(blueprint.observability).map((item, index) => <li key={`full-observability-${index}`}>{item}</li>)}</ul></div>
            <div><strong>技术栈与部署</strong><ul>{prdItems(blueprint.technology_and_deployment).map((item, index) => <li key={`full-technology-${index}`}>{item}</li>)}</ul></div>
            <div><strong>系统提示词草案</strong><p>{String(blueprint.system_prompt_draft ?? "待确认")}</p></div>
          </div>

          <h5>工具清单</h5>
          <div className="prd-full-tool-list">
            {toolCatalog.map((item, index) => (
              <article key={`full-tool-${index}`}>
                <header><strong>{String(item.name ?? `工具 ${index + 1}`)}</strong><span>{String(item.layer ?? "能力集成层")}</span></header>
                <p>{String(item.purpose ?? "待确认")}</p>
                <dl>
                  <div><dt>输入</dt><dd>{String(item.input ?? "待确认")}</dd></div>
                  <div><dt>输出</dt><dd>{String(item.output ?? "待确认")}</dd></div>
                  <div><dt>副作用</dt><dd>{String(item.side_effect ?? "待确认")}</dd></div>
                  <div><dt>权限</dt><dd>{String(item.permission ?? "待确认")}</dd></div>
                </dl>
              </article>
            ))}
          </div>

          <h5>代码生成计划</h5>
          <div className="prd-full-document-grid prd-full-agent-grid">
            <div><strong>骨架</strong><ul>{prdItems(codePlan.skeleton).map((item, index) => <li key={`full-skeleton-${index}`}>{item}</li>)}</ul></div>
            <div><strong>硬化</strong><ul>{prdItems(codePlan.hardening).map((item, index) => <li key={`full-hardening-${index}`}>{item}</li>)}</ul></div>
            <div><strong>产品化</strong><ul>{prdItems(codePlan.productization).map((item, index) => <li key={`full-productization-${index}`}>{item}</li>)}</ul></div>
            <div><strong>确认门</strong><p>{String(codePlan.confirmation_gate ?? "方案确认前不生成产品代码")}</p></div>
          </div>
        </section>
      )}
    </article>
  );
}

function GenericPrdPreview() {
  return (
    <article className="prd-live-document prd-placeholder-document" aria-label="通用产品需求文档预览">
      <div className="prd-document-heading">
        <h2>{GENERIC_PRD_PREVIEW.title}</h2>
        <p>{withoutTerminalPeriods(String(GENERIC_PRD_PREVIEW.summary))}</p>
        <div className="prd-template-tags" aria-label="番茄时间闹钟模板标签">
          <span><Clock3 size={14} />25 分钟专注</span>
          <span><Coffee size={14} />5 分钟休息</span>
          <span><MonitorSmartphone size={14} />网页工具</span>
          <span><BellRing size={14} />到时提醒</span>
        </div>
      </div>
      <PrdStructuredContent value={GENERIC_PRD_PREVIEW} placeholder />
    </article>
  );
}

export function M1ARequirements({ project, onProjectChange, onRefresh, onError, onNotice, onNavigate, focus = "idea" }: StageProps & { focus?: "idea" | "solution" }) {
  const [artifacts, setArtifacts] = useState<Artifact[]>(project.latest_artifacts ?? []);
  const [answer, setAnswer] = useState("");
  const [failedMessage, setFailedMessage] = useState("");
  const [revision, setRevision] = useState("");
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [fastMode, setFastMode] = useCodexFastMode();
  const [model, setModel] = useState("5.6 Sol");
  const [reasoningEffort, setReasoningEffort] = useState<(typeof CODEX_EFFORTS)[number]>("中");
  const [listening, setListening] = useState(false);
  const [openComposerMenu, setOpenComposerMenu] = useState<"models" | null>(null);
  const [draft, setDraft] = useState<JsonObject | null>(null);
  const [conversationId, setConversationId] = useState("");
  const displayedConversationId = useRef("");
  const [, setConversationTitle] = useState("新对话");
  const [conversationHistory, setConversationHistory] = useState<CodexConversationSummary[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [generationPhase, setGenerationPhase] = useState<GenerationPhase>("idle");
  const [thinkingElapsedSeconds, setThinkingElapsedSeconds] = useState(0);
  const [reasoningSummary, setReasoningSummary] = useState("");
  const [liveReply, setLiveReply] = useState("");
  const [clarifyingQuestion, setClarifyingQuestion] = useState<CodexClarifyingQuestion | null>(null);
  const [selectedChoices, setSelectedChoices] = useState<string[]>([]);
  const [choiceSupplement, setChoiceSupplement] = useState("");
  const [outputStream, setOutputStream] = useState<OutputStream | null>(null);
  const [visibleOutputCharacters, setVisibleOutputCharacters] = useState(0);
  const [previewResetForConversation, setPreviewResetForConversation] = useState(false);
  const [fullPrdPreviewOpen, setFullPrdPreviewOpen] = useState(false);
  const answerRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const composerRef = useRef<HTMLFormElement>(null);
  const historyRef = useRef<HTMLDivElement>(null);
  const fullPrdCloseRef = useRef<HTMLButtonElement>(null);
  const voiceRecognitionRef = useRef<VoiceRecognition | null>(null);
  const [conversation, setConversation] = useState<ConversationItem[]>([
    { id: "welcome", role: "assistant", text: "把你的产品想法告诉我。我会一次只确认一个关键问题，并在右侧持续整理成 PRD。" },
  ]);

  useEffect(() => {
    let active = true;
    Promise.all([api.artifacts(project.id), api.codexConversation(project.id), api.codexConversations(project.id)])
      .then(([artifactResponse, codexResponse, historyResponse]) => {
        if (!active) return;
        setArtifacts(artifactResponse.items);
        applyConversation(codexResponse);
        setConversationHistory(historyResponse.items);
      })
      .catch(onError);
    return () => { active = false; };
  }, [onError, project.id, project.current_artifact_version]);

  useEffect(() => () => {
    voiceRecognitionRef.current?.abort();
  }, []);

  useEffect(() => {
    if (generationPhase !== "thinking") return;
    const timer = window.setInterval(() => setThinkingElapsedSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [generationPhase]);

  useEffect(() => {
    if (!outputStream || generationPhase !== "writing") return;
    const finishWriting = () => {
      setVisibleOutputCharacters(outputStream.totalCharacters);
      setGenerationPhase("complete");
      setGenerating(false);
      setBusy(false);
    };
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReducedMotion || outputStream.totalCharacters <= 0) {
      const completionTimer = window.setTimeout(finishWriting, 0);
      return () => window.clearTimeout(completionTimer);
    }
    const delay = 11;
    let nextVisibleCharacters = 0;
    const timer = window.setInterval(() => {
      nextVisibleCharacters = Math.min(outputStream.totalCharacters, nextVisibleCharacters + Math.max(1, Math.ceil(outputStream.totalCharacters / 100)));
      setVisibleOutputCharacters(nextVisibleCharacters);
      if (nextVisibleCharacters >= outputStream.totalCharacters) {
        window.clearInterval(timer);
        finishWriting();
      }
    }, delay);
    return () => window.clearInterval(timer);
  }, [generationPhase, outputStream]);

  useEffect(() => {
    const textarea = answerRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 192)}px`;
  }, [answer]);

  useEffect(() => {
    function closeComposerMenu(event: MouseEvent) {
      if (composerRef.current && !composerRef.current.contains(event.target as Node)) setOpenComposerMenu(null);
      if (historyRef.current && !historyRef.current.contains(event.target as Node)) setHistoryOpen(false);
    }
    function closeComposerMenuWithEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpenComposerMenu(null);
        setHistoryOpen(false);
        setFullPrdPreviewOpen(false);
      }
    }
    document.addEventListener("mousedown", closeComposerMenu);
    document.addEventListener("keydown", closeComposerMenuWithEscape);
    return () => {
      document.removeEventListener("mousedown", closeComposerMenu);
      document.removeEventListener("keydown", closeComposerMenuWithEscape);
    };
  }, []);

  useEffect(() => {
    if (!fullPrdPreviewOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => fullPrdCloseRef.current?.focus());
    return () => { document.body.style.overflow = previousOverflow; };
  }, [fullPrdPreviewOpen]);

  const latestPrd = useMemo(() => artifacts.filter((item) => item.type === "prd").sort((a, b) => b.version - a.version)[0], [artifacts]);
  const latestSolution = useMemo(() => artifacts.filter((item) => item.type === "solution").sort((a, b) => b.version - a.version)[0], [artifacts]);
  const activeType = focus === "solution" ? "solution" : "prd";
  const currentArtifact = activeType === "prd" ? latestPrd : latestSolution;
  const hasStartedConversation = conversation.some((item) => item.role === "user");
  const storedPreviewContent = activeType === "prd"
    ? previewResetForConversation || Boolean(clarifyingQuestion) || (hasStartedConversation && !draft)
      ? null
      : draft ?? currentArtifact?.content
    : currentArtifact?.content;
  const previewContent = activeType === "prd" && outputStream
    ? revealPrdContent(outputStream.draft, visibleOutputCharacters)
    : storedPreviewContent;
  const isTypingPreview = Boolean(outputStream && visibleOutputCharacters < outputStream.totalCharacters);
  const draftIsUnpublished = Boolean(
    activeType === "prd"
    && draft
    && (!currentArtifact || JSON.stringify(draft) !== JSON.stringify(currentArtifact.content)),
  );
  const canChatWithCodex = project.stage === "REQUIREMENTS" || project.stage === "PRD_REVIEW";
  const showGenericPrdPreview = !outputStream && !storedPreviewContent;
  const canReviewCurrentPrd = Boolean(
    currentArtifact
    && draft
    && project.stage === "PRD_REVIEW"
    && hasStartedConversation
    && !previewResetForConversation
    && !clarifyingQuestion
    && !draftIsUnpublished
    && !isTypingPreview,
  );
  const streamedAssistant = outputStream
    ? conversation.find((item) => item.id === outputStream.assistantMessageId)
    : undefined;
  const starterPrompts = [
    { label: "梳理产品目标和核心问题", icon: CircleHelp },
    { label: "定义目标用户和使用场景", icon: Search },
    { label: "设计首版功能和操作流程", icon: MessageSquareText },
    { label: "审查并完善产品需求", icon: FileText },
    { label: "生成可确认的产品需求文档", icon: Lightbulb },
  ] as const;

  function applyConversation(response: CodexConversationResponse, animate = false) {
    if (response.conversation_id !== displayedConversationId.current) {
      setReasoningSummary("");
      setGenerationPhase("idle");
    }
    displayedConversationId.current = response.conversation_id;
    setConversationId(response.conversation_id);
    setConversationTitle(response.title);
    const nextConversation = response.messages.map((item) => ({ id: item.id, role: item.role, text: item.content }));
    setConversation(nextConversation);
    const lastMessage = nextConversation.at(-1);
    setFailedMessage(lastMessage?.id.startsWith("failed:") ? lastMessage.text : "");
    setDraft(response.draft);
    setClarifyingQuestion(response.current_question ?? null);
    setSelectedChoices([]);
    setChoiceSupplement("");
    setPreviewResetForConversation(!nextConversation.some((item) => item.role === "user"));
    if (animate && response.draft) {
      setPreviewResetForConversation(false);
      const assistantMessage = [...nextConversation].reverse().find((item) => item.role === "assistant");
      if (assistantMessage) {
        const draftCharacters = prdCharacterCount(response.draft);
        const assistantCharacters = Array.from(assistantMessage.text).length;
        setVisibleOutputCharacters(0);
        setOutputStream({
          id: `${response.conversation_id}-${assistantMessage.id}-${Date.now()}`,
          assistantMessageId: assistantMessage.id,
          assistantText: assistantMessage.text,
          draft: response.draft,
          totalCharacters: Math.max(draftCharacters, assistantCharacters),
        });
        setGenerationPhase("writing");
      }
    }
  }

  async function refreshConversationHistory() {
    const response = await api.codexConversations(project.id);
    setConversationHistory(response.items);
  }

  function leaveGenerationRunningInBackground() {
    setGenerating(false);
    setLiveReply("");
    setReasoningSummary("");
    setGenerationPhase("idle");
    setOutputStream(null);
    setVisibleOutputCharacters(0);
  }

  async function createConversation() {
    if (busy && !generating) return;
    if (generating) leaveGenerationRunningInBackground();
    setBusy(true);
    setPreviewResetForConversation(true);
    try {
      const response = await api.createCodexConversation(project.id);
      applyConversation(response);
      setAnswer("");
      setHistoryOpen(false);
      await refreshConversationHistory();
      requestAnimationFrame(() => answerRef.current?.focus());
    } catch (value) {
      onError(value);
    } finally {
      setBusy(false);
    }
  }

  async function activateConversation(nextConversationId: string) {
    if (nextConversationId === conversationId) {
      setHistoryOpen(false);
      return;
    }
    if (busy && !generating) return;
    if (generating) leaveGenerationRunningInBackground();
    setBusy(true);
    try {
      const response = await api.activateCodexConversation(project.id, nextConversationId);
      applyConversation(response);
      setAnswer("");
      setHistoryOpen(false);
      await refreshConversationHistory();
    } catch (value) {
      onError(value);
    } finally {
      setBusy(false);
    }
  }

  async function submitAnswer(messageOverride?: string) {
    const text = (messageOverride ?? answer).trim();
    if (!text || busy || !conversationId || getRequirementRun(project.id, conversationId)) return;
    setFailedMessage("");
    setClarifyingQuestion(null);
    setBusy(true);
    setGenerating(true);
    setGenerationPhase("thinking");
    setThinkingElapsedSeconds(0);
    setReasoningSummary("");
    setLiveReply("");
    setOutputStream(null);
    setVisibleOutputCharacters(0);
    setAnswer("");
    setSelectedChoices([]);
    if (!hasStartedConversation) setConversationTitle(text);
    setConversation((items) => {
      const last = items.at(-1);
      const previous = failedMessage === text && last?.role === "user" && last.text === text ? items.slice(0, -1) : items;
      return [...previous, { id: `user-${Date.now()}`, role: "user", text }];
    });
    startRequirementRun(project.id, conversationId, text, {
      model: CODEX_MODEL_IDS[model],
      reasoningEffort: CODEX_REASONING_EFFORT_IDS[reasoningEffort],
          serviceTier: fastMode ? "fast" : "default",
    });
  }

  // Reattach to this conversation after navigating back. No background callback
  // may update another project's state or replace the active conversation.
  useEffect(() => {
    const sync = () => {
      const run = getRequirementRun(project.id, conversationId);
      if (!run) return;
      if (!run.settled) {
        setBusy(true);
        setGenerating(true);
        setGenerationPhase("thinking");
        setThinkingElapsedSeconds(Math.floor((Date.now() - run.startedAt) / 1000));
        setReasoningSummary(run.summary);
        setLiveReply(run.reply);
        return;
      }
      clearRequirementRun(project.id, conversationId);
      setReasoningSummary(run.summary);
      setLiveReply("");
      setGenerating(false);
      setBusy(false);
      setGenerationPhase("idle");
      if (run.response) {
        const response = run.response;
        applyConversation(response);
        onProjectChange(response.project);
        if (response.artifact) {
          setArtifacts((items) => [response.artifact as Artifact, ...items]);
          onNotice("Codex 已生成正式 PRD，请在右侧检查后确认。");
        }
        void refreshConversationHistory().catch(onError);
      } else if (run.error && !(run.error instanceof DOMException && run.error.name === "AbortError")) {
        setFailedMessage(run.message);
        setClarifyingQuestion(null);
        onError(run.error);
      }
    };
    const timer = window.setInterval(sync, 200);
    return () => window.clearInterval(timer);
  });

  function toggleChoice(option: string) {
    if (!clarifyingQuestion || busy) return;
    setSelectedChoices((items) => {
      const nextItems = clarifyingQuestion.mode === "single"
        ? [option]
        : items.includes(option)
          ? items.filter((item) => item !== option)
          : [...items, option];
      if (!nextItems.some((item) => item.includes("其他"))) setChoiceSupplement("");
      return nextItems;
    });
  }

  function submitChoices() {
    if (!clarifyingQuestion || selectedChoices.length === 0) return;
    const submittedChoices = selectedChoices.map((option) => option.includes("其他")
      ? `其他：${choiceSupplement.trim()}`
      : option);
    if (selectedChoices.some((option) => option.includes("其他")) && !choiceSupplement.trim()) return;
    const response = clarifyingQuestion.mode === "multiple"
      ? `我选择：${submittedChoices.join("、")}`
      : submittedChoices[0];
    void submitAnswer(`${clarifyingQuestion.prompt}\n${response}`);
  }

  function stopGeneration() {
    const run = getRequirementRun(project.id, conversationId);
    if (run) {
      run.controller.abort();
      clearRequirementRun(project.id, conversationId);
      setReasoningSummary(run.summary);
      setLiveReply("");
      setGenerationPhase("idle");
      setGenerating(false);
      setBusy(false);
      return;
    }
    if (outputStream) {
      setVisibleOutputCharacters(outputStream.totalCharacters);
      setGenerationPhase("complete");
      setGenerating(false);
      setBusy(false);
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
        setAnswer((value) => `${value}${value.trim() ? " " : ""}${transcript.trim()}`);
        requestAnimationFrame(() => answerRef.current?.focus());
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

  async function uploadRequirementFile(file: File) {
    setBusy(true);
    try {
      const response = await api.uploadRequirement(project.id, file);
      onProjectChange(response.project);
      setConversation((items) => [...items,
        { id: `upload-${Date.now()}`, role: "user", text: `已上传文件：${file.name}` },
        { id: `upload-reply-${Date.now()}`, role: "assistant", text: response.reply },
      ]);
      if (response.artifact) {
        setArtifacts((items) => [response.artifact as Artifact, ...items]);
        onNotice("文件已上传并整理为可确认的产品需求。");
      }
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  async function decide(type: "prd" | "solution", decision: "confirm" | "revise") {
    const artifact = type === "prd" ? latestPrd : latestSolution;
    if (!artifact) return;
    if (decision === "revise" && !revision.trim()) {
      onError({ code: "REVISION_REQUIRED", userMessage: "请先写下你希望修改的内容。", message: "revision required", retryable: false });
      return;
    }
    setBusy(true);
    try {
      const response = await api.confirmArtifact(project.id, type, artifact.id, decision, revision.trim());
      onProjectChange(response.project);
      setRevision("");
      await onRefresh();
      const list = await api.artifacts(project.id);
      setArtifacts(list.items);
      if (type === "prd" && decision === "confirm") {
        onNotice("产品需求已确认，推荐产品方案已经生成。");
      } else if (type === "solution" && decision === "confirm") {
        onNotice("产品方案已确认，工厂可以开始生成产品了。");
        onNavigate("m1c");
      } else {
        onNotice("修改意见已保存，新版本已经生成。");
      }
    } catch (value) { onError(value); } finally { setBusy(false); }
  }

  if (focus === "idea") {
    const liveIdea = answer.trim() || project.idea.trim();
    return (
      <>
      <section className="prd-copilot-workbench" aria-label="Codex PRD 工作台">
        <div className="prd-assistant-pane codex-assistant-surface" aria-label="Codex 产品助手">
          <div ref={historyRef} className="codex-conversation-toolbar">
            <div className="codex-conversation-actions">
              <button type="button" onClick={() => setHistoryOpen((value) => !value)} disabled={busy && !generating} aria-label="历史对话" aria-expanded={historyOpen} title="历史对话"><History size={18} /></button>
              <button type="button" onClick={() => void createConversation()} disabled={busy && !generating} aria-label="新建对话" title="新建对话"><SquarePen size={17} /></button>
            </div>
            {historyOpen && (
              <div className="codex-history-popover" role="dialog" aria-label="历史对话">
                <div className="codex-history-heading"><strong>历史对话</strong><span>{conversationHistory.length} 条</span></div>
                <div className="codex-history-list">
                  {conversationHistory.map((item) => (
                    <button key={item.id} type="button" className={item.active ? "active" : ""} onClick={() => void activateConversation(item.id)} aria-current={item.active ? "true" : undefined}>
                      <span><strong>{item.title}</strong><small>{new Date(item.updated_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })} · {item.message_count} 轮</small></span>
                      {item.active && <i>当前</i>}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="codex-conversation-scroll">
            {!hasStartedConversation ? (
              <div className="codex-welcome">
                <div className="codex-welcome-heading">
                  <span className="codex-welcome-mark"><CodexMark /></span>
                  <h1><span>我是您的 AI 产品助手</span><span>我能帮您创建什么？</span></h1>
                </div>
                <ul className="codex-guide-list" aria-label="产品助手能力">
                  {starterPrompts.map(({ label, icon: Icon }) => (
                    <li key={label}>
                      <Icon size={22} />
                      <span>{label}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="prd-chat-thread codex-chat-thread" aria-live="polite">
                {conversation.filter((item) => item.id !== "welcome" && item.id !== outputStream?.assistantMessageId).map((item) => (
                  <article key={item.id} className={item.role}>
                    <div className="codex-message-content"><p>{item.text}</p></div>
                  </article>
                ))}
                <PrdThinkingProgress
                  phase={generationPhase}
                  elapsedSeconds={thinkingElapsedSeconds}
                  reasoningSummary={reasoningSummary}
                />
                {generating && liveReply && <article className="assistant is-streaming"><div className="codex-message-content"><p>{liveReply}<span className="prd-typing-cursor" aria-hidden="true" /></p></div></article>}
                {streamedAssistant && (
                  <article key={streamedAssistant.id} className="assistant is-streaming">
                    <div className="codex-message-content">
                      <p>{Array.from(outputStream?.assistantText ?? streamedAssistant.text).slice(0, visibleOutputCharacters).join("")}{isTypingPreview && <span className="prd-typing-cursor" aria-hidden="true" />}</p>
                    </div>
                  </article>
                )}
                {failedMessage && !generating && <section className="codex-choice-question" aria-label="生成失败重试">
                  <strong>这次请求未完成</strong>
                  <p>已保留你的需求，可以直接重试，无需重新回答。</p>
                  <button className="codex-choice-submit" type="button" disabled={busy} onClick={() => void submitAnswer(failedMessage)}>重试这次请求</button>
                </section>}
                {clarifyingQuestion && !generating && !failedMessage && (
                  <CodexChoiceQuestion
                    question={clarifyingQuestion}
                    selected={selectedChoices}
                    supplement={choiceSupplement}
                    disabled={busy}
                    onToggle={toggleChoice}
                    onSupplementChange={setChoiceSupplement}
                    onSubmit={submitChoices}
                  />
                )}
              </div>
            )}
          </div>

          {canChatWithCodex ? (
            <form ref={composerRef} className="codex-command-composer" onSubmit={(event) => { event.preventDefault(); void submitAnswer(); }}>
              <div className="codex-composer-box">
                <textarea
                  ref={answerRef}
                  id="requirement-answer"
                  value={answer}
                  onChange={(event) => setAnswer(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  placeholder={listening ? "正在聆听…" : "输入产品点子，或上传尚未完善的 PRD，我来帮你生成完整的 PRD 文档"}
                  aria-label="向 Codex 描述产品需求"
                  maxLength={10000}
                />
                <div className="codex-composer-toolbar">
                  <button className="codex-tool-button codex-add-button" type="button" onClick={() => fileInputRef.current?.click()} aria-label="添加文件" title="上传文档、代码或压缩包" disabled={busy}><Plus size={20} /></button>
                  <input
                    ref={fileInputRef}
                    className="codex-file-input"
                    type="file"
                    hidden
                    accept={SUPPORTED_UPLOAD_ACCEPT}
                    disabled={busy}
                    onChange={(event) => {
                      const file = event.currentTarget.files?.[0];
                      event.currentTarget.value = "";
                      if (file) void uploadRequirementFile(file);
                    }}
                  />
                  <CodexModelSettings fastMode={fastMode} onFastModeChange={setFastMode} model={model} effort={reasoningEffort} onModelChange={setModel} onEffortChange={setReasoningEffort} open={openComposerMenu === "models"} onOpenChange={(open) => setOpenComposerMenu(open ? "models" : null)} disabled={busy} />
                  <button className={`codex-tool-button codex-mic-button ${listening ? "listening" : ""}`} type="button" onClick={toggleDictation} aria-label={listening ? "停止听写" : "开始听写"} aria-pressed={listening} disabled={busy}><Mic size={19} /></button>
                  {generating ? (
                    <button className="codex-stop-button" type="button" onClick={stopGeneration} aria-label="停止生成"><Square size={12} fill="currentColor" /></button>
                  ) : (
                    <button className="codex-send-button" type="submit" aria-label="发送给 Codex" disabled={!answer.trim() || busy}><ArrowUp size={18} /></button>
                  )}
                </div>
              </div>
            </form>
          ) : (
            <div className="prd-assistant-complete"><Check size={16} /><span>信息已整理，请在右侧检查并确认 PRD。</span></div>
          )}
        </div>

        <div className={`prd-preview-pane${showGenericPrdPreview ? " is-placeholder" : ""}`}>
          <header className={`prd-pane-header prd-preview-header${showGenericPrdPreview ? " is-placeholder" : ""}`}>
            <span><FileText size={18} /></span>
            <div>
              <strong>产品需求文档</strong>
              <small>{showGenericPrdPreview ? "开始对话后由真实需求替换" : isTypingPreview ? "正在逐字生成" : draftIsUnpublished ? "实时草稿" : currentArtifact ? `第 ${currentArtifact.version} 版` : "随对话实时更新"}</small>
            </div>
            {!showGenericPrdPreview && <StatusPill status={isTypingPreview || busy ? "running" : draftIsUnpublished ? "open" : currentArtifact?.status ?? "open"} />}
          </header>

          <div className="prd-document-scroll">
            {showGenericPrdPreview ? <GenericPrdPreview /> : <article className="prd-live-document">
              <div className="prd-document-heading">
                <h2>{String(previewContent?.title ?? "")}{isTypingPreview && !previewContent?.summary && <span className="prd-typing-cursor" aria-hidden="true" />}</h2>
                <p>{withoutTerminalPeriods(String(previewContent?.summary ?? ""))}{isTypingPreview && Boolean(previewContent?.summary) && <span className="prd-typing-cursor" aria-hidden="true" />}</p>
              </div>

              {previewContent ? (
                <PrdStructuredContent value={previewContent} streaming={isTypingPreview} />
              ) : (
                <div className="prd-draft-content">
                  <section>
                    <div><i>01</i><h3>产品目标</h3></div>
                    <p>{liveIdea || "在左侧描述产品想法后，这里会开始形成产品目标。"}</p>
                  </section>
                  <section>
                    <div><i>02</i><h3>目标用户与核心场景</h3></div>
                    <p>Codex 将通过追问补齐目标用户、使用场景和需要解决的问题。</p>
                  </section>
                  <section>
                    <div><i>03</i><h3>首版产品范围</h3></div>
                    <ul><li>核心使用流程</li><li>首版主要功能</li><li>暂不包含的范围</li></ul>
                  </section>
                  <section>
                    <div><i>04</i><h3>完成标准</h3></div>
                    <p>需求信息齐全后，Codex 会生成可以逐项检查和确认的正式版本。</p>
                  </section>
                </div>
              )}

              {canReviewCurrentPrd && (
                <>
                <div className="prd-full-preview-entry">
                  <button type="button" onClick={() => setFullPrdPreviewOpen(true)} aria-haspopup="dialog">
                    <FileText size={18} aria-hidden="true" />
                    <span><strong>预览完整 PRD 文档</strong></span>
                    <ChevronRight size={17} aria-hidden="true" />
                  </button>
                </div>
                <div className="artifact-decision prd-document-decision">
                  <label>需要修改的内容<textarea value={revision} onChange={(event) => setRevision(event.target.value)} placeholder="例如：首版先不做用户登录，把核心流程跑通。" /></label>
                  <div><button className="ghost-button" type="button" onClick={() => void decide("prd", "revise")} disabled={busy}><PencilLine size={15} />按意见生成新版</button></div>
                </div>
                </>
              )}
            </article>}
          </div>
          {canReviewCurrentPrd && (
            <footer className="prd-confirmation-bar" aria-label="产品需求确认操作">
              <div><strong>产品需求已整理完成</strong><span>确认后自动生成推荐方案，并进入第 2 步</span></div>
              <button className="primary-button" type="button" onClick={() => void decide("prd", "confirm")} disabled={busy}>确认产品需求<ArrowRight size={16} /></button>
            </footer>
          )}
        </div>
      </section>
      {fullPrdPreviewOpen && currentArtifact && (
        <div className="prd-full-preview-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setFullPrdPreviewOpen(false); }}>
          <section className="prd-full-preview-dialog" role="dialog" aria-modal="true" aria-labelledby="full-prd-preview-title">
            <header>
              <div className="prd-full-preview-dialog-heading">
                <span aria-hidden="true"><FileText size={20} /></span>
                <div><h2 id="full-prd-preview-title">完整 PRD 文档</h2><p>第 {currentArtifact.version} 版 · 该制品将用于方案、生成与部署流程</p></div>
              </div>
              <button ref={fullPrdCloseRef} type="button" onClick={() => setFullPrdPreviewOpen(false)} aria-label="关闭完整 PRD 预览"><X size={20} /></button>
            </header>
            <div className="prd-full-preview-scroll"><FullPrdDocument artifact={currentArtifact} /></div>
          </section>
        </div>
      )}
      </>
    );
  }

  return (
    <>
      <StageIntro
        eyebrow="第 2 步 · 确认方案"
        title="先体验低保真方案，再生成高保真 UI"
        description="根据已确认 PRD 生成关键界面故事板。先判断页面结构、操作和状态是否合理，确认后再进入真实 HTML 生成。"
      />

      <div className="two-column-stage requirements-layout solution-stage-layout">
        <Panel className="artifact-panel">
          <div className="artifact-title-row">
            <span><MessageSquareText size={17} /></span>
            <div><strong>低保真可视化方案</strong><small>{currentArtifact ? `第 ${currentArtifact.version} 版` : "等待生成"}</small></div>
          </div>
          {currentArtifact ? (
            <div className="artifact-document">
              {activeType === "prd" && <div className="document-meta"><span>产品理解与首版范围</span><StatusPill status={currentArtifact.status} /></div>}
              {activeType === "prd"
                ? <ObjectList value={currentArtifact.content} />
                : <SolutionVisualDecisionView projectId={project.id} prdContent={latestPrd?.content ?? {}} />}
              {((activeType === "prd" && project.stage === "PRD_REVIEW") || (activeType === "solution" && project.stage === "SOLUTION_REVIEW")) && (
                <div className="artifact-decision">
                  <label>{activeType === "solution" ? "想调整哪里？用你自己的话描述即可" : "哪里需要修改？"}<textarea value={revision} onChange={(event) => setRevision(event.target.value)} placeholder={activeType === "solution" ? "例如：首版先不做登录；数据只保存在当前浏览器。" : "例如：首版先不做用户登录，把核心分析流程跑通。"} /></label>
                  <div><button className="ghost-button" type="button" onClick={() => void decide(activeType, "revise")} disabled={busy}><PencilLine size={15} />{activeType === "solution" ? "按意见更新方案" : "按意见生成新版"}</button><button className="primary-button" type="button" onClick={() => void decide(activeType, "confirm")} disabled={busy}>{activeType === "prd" ? "确认产品需求" : "方案没问题，生成高保真 UI"}<ArrowRight size={16} /></button></div>
                </div>
              )}
              {project.stage !== "SOLUTION_REVIEW" && activeType === "solution" && <button className="primary-button wide solution-next-build" type="button" onClick={() => onNavigate("m1c")}>进入下一步，生成高保真 UI<ArrowRight size={16} /></button>}
            </div>
          ) : (
            <EmptyState title={activeType === "prd" ? "PRD 预览会出现在这里" : "确认产品需求后生成方案"} description={activeType === "prd" ? "左侧用自然语言描述，或上传已有 PRD，提交后会直接生成预览。" : "方案会解释功能范围、使用流程、费用、权限、风险和实现方式。"} />
          )}
        </Panel>
      </div>
    </>
  );
}
