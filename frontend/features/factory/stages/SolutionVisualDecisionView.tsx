"use client";

import { useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BellRing,
  Check,
  CircleCheckBig,
  Clock3,
  Code2,
  Database,
  MousePointerClick,
  Pause,
  Play,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import type { JsonObject } from "@/lib/api/types";
import {
  UiStylePicker,
  loadUiStylePreference,
  saveUiStylePreference,
  type UiStyleKey,
} from "../UiStylePicker";

type StoryFrame = {
  key: string;
  eyebrow: string;
  title: string;
  description: string;
  action: string;
  result: string;
  timer?: string;
  mode?: "focus" | "pause" | "short-break" | "long-break" | "summary";
};

type SolutionVisualDecisionViewProps = {
  projectId: string;
  content: JsonObject;
  prdContent: JsonObject;
  prdTitle: string;
};

function recordOf(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
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

function timerFrames(): StoryFrame[] {
  return [
    { key: "ready", eyebrow: "界面 1 · 准备", title: "准备开始专注", description: "用户一打开网页就能看到当前模式、25 分钟和唯一主操作。", action: "开始专注", result: "进入专注倒计时，并记录这一轮的开始时间", timer: "25:00", mode: "focus" },
    { key: "running", eyebrow: "界面 2 · 专注中", title: "专注倒计时", description: "时间是视觉中心，同时保留暂停和提前结束，避免用户迷失。", action: "暂停", result: "冻结当前剩余时间，显示继续与重置操作", timer: "24:38", mode: "focus" },
    { key: "paused", eyebrow: "界面 3 · 已暂停", title: "暂停后可继续", description: "页面明确告诉用户计时已停，不会把暂停误认为仍在运行。", action: "继续", result: "从保存的剩余时间继续本轮专注", timer: "18:42", mode: "pause" },
    { key: "short-break", eyebrow: "界面 4 · 短休息", title: "完成一轮，进入休息", description: "专注结束后给出到时提醒，并把下一步变成 5 分钟短休息。", action: "开始休息", result: "进入短休息倒计时，当日完成轮数加一", timer: "05:00", mode: "short-break" },
    { key: "long-break", eyebrow: "界面 5 · 长休息", title: "第 4 轮后的长休息", description: "完成四轮专注后自动推荐 15 分钟长休息，节奏无需用户计算。", action: "开始长休息", result: "进入 15 分钟长休息，完成后开启新一组", timer: "15:00", mode: "long-break" },
    { key: "summary", eyebrow: "界面 6 · 今日记录", title: "查看今天的完成情况", description: "用户能看到完成轮数和专注分钟数，数据留在当前浏览器。", action: "开始新一轮", result: "回到 25 分钟准备状态，保留今日统计", mode: "summary" },
  ];
}

function genericFrames(prdContent: JsonObject): StoryFrame[] {
  const coreFlow = linesOf(prdContent.core_flow);
  const features = linesOf(prdContent.features);
  const source = coreFlow.length > 0 ? coreFlow : features.length > 0 ? features : ["进入产品", "完成核心操作", "查看结果"];
  return source.slice(0, 6).map((item, index, items) => ({
    key: `flow-${index + 1}`,
    eyebrow: `界面 ${index + 1} · ${index === 0 ? "开始" : index === items.length - 1 ? "结果" : "操作"}`,
    title: item.length > 22 ? `${item.slice(0, 22)}…` : item,
    description: `这个界面负责让用户${item.replace(/^用户/, "")}，只展示完成当前任务所需的信息。`,
    action: index === items.length - 1 ? "再次开始" : "完成并继续",
    result: index === items.length - 1 ? "保存当前结果并回到可继续使用的状态" : `进入下一界面：${items[index + 1]}`,
  }));
}

function TimerWireframe({ frame, onAdvance }: { frame: StoryFrame; onAdvance: () => void }) {
  const summary = frame.mode === "summary";
  return (
    <div className={`solution-wireframe-screen timer ${frame.mode ?? "focus"}`}>
      <header>
        <span className="wireframe-brand"><i />西瓜时间</span>
        <nav><span className="active">计时</span><span>今日记录</span><span>设置</span></nav>
      </header>
      <main>
        <div className="wireframe-mode-tabs"><span className={frame.mode === "focus" || frame.mode === "pause" ? "active" : ""}>专注</span><span className={frame.mode === "short-break" ? "active" : ""}>短休息</span><span className={frame.mode === "long-break" ? "active" : ""}>长休息</span></div>
        {summary ? (
          <div className="wireframe-summary">
            <small>今天</small><strong>4</strong><span>轮专注 · 100 分钟</span>
            <div><i /><i /><i /><i /></div>
          </div>
        ) : (
          <>
            <div className="wireframe-clock"><small>{frame.mode === "pause" ? "计时已暂停" : frame.mode === "focus" ? "保持专注" : "好好休息"}</small><strong>{frame.timer}</strong><span><i style={{ width: frame.key === "running" ? "34%" : frame.key === "paused" ? "58%" : "4%" }} /></span></div>
            <div className="wireframe-rounds"><span>今日完成 <strong>{frame.mode === "short-break" || frame.mode === "long-break" ? "4" : "3"}</strong> 轮</span><span>下一阶段：{frame.mode === "focus" || frame.mode === "pause" ? "短休息" : "专注"}</span></div>
          </>
        )}
        <div className="wireframe-actions">
          {frame.key !== "ready" && frame.key !== "summary" && <button type="button" className="secondary" aria-label="次要操作"><RotateCcw size={15} />重置</button>}
          <button type="button" className="primary" onClick={onAdvance}>{frame.key === "running" ? <Pause size={16} /> : <Play size={16} />}{frame.action}</button>
        </div>
      </main>
    </div>
  );
}

function GenericWireframe({ frame, productTitle, onAdvance }: { frame: StoryFrame; productTitle: string; onAdvance: () => void }) {
  return (
    <div className="solution-wireframe-screen generic">
      <header><span className="wireframe-brand"><i />{productTitle}</span><nav><span className="active">首页</span><span>记录</span><span>设置</span></nav></header>
      <main>
        <span className="generic-wireframe-kicker">{frame.eyebrow}</span>
        <h3>{frame.title}</h3>
        <p>{frame.description}</p>
        <div className="generic-wireframe-grid"><span /><span /><span /></div>
        <button type="button" className="primary" onClick={onAdvance}><MousePointerClick size={16} />{frame.action}</button>
      </main>
    </div>
  );
}

export function SolutionVisualDecisionView({ projectId, content, prdContent, prdTitle }: SolutionVisualDecisionViewProps) {
  const prdScope = recordOf(prdContent.scope);
  const fullDocument = recordOf(prdContent.full_document);
  const sourceText = JSON.stringify({ content, prdContent });
  const isTimer = /番茄|倒计时|计时器|专注.{0,8}休息|25\s*分钟/.test(sourceText);
  const frames = useMemo(() => isTimer ? timerFrames() : genericFrames(prdContent), [isTimer, prdContent]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [uiStyleKey, setUiStyleKey] = useState<UiStyleKey>(() => loadUiStylePreference(projectId) ?? "pirsch-paper");
  const active = frames[activeIndex] ?? frames[0];
  const included = linesOf(content.product_scope, prdScope.included).slice(0, 5);
  const excluded = linesOf(content.deferred, prdScope.excluded).slice(0, 4);
  const assumptions = linesOf(prdContent.assumptions);
  const artifactRisks = linesOf(content.risks, fullDocument.open_questions)
    .filter((item) => !/任意代码沙箱|本地预览|真实 Key|模型效果|冒烟/.test(item))
    .slice(0, 3);
  const risks = isTimer
    ? ["浏览器通知需要用户授权；拒绝后不影响页面计时", "关闭浏览器后，系统级到时提醒可能受设备设置限制", "首版记录只保存在当前浏览器，不支持跨设备同步"]
    : artifactRisks;
  const accounts = linesOf(content.external_accounts);
  const dataSummary = assumptions.find((item) => /本地|浏览器|设备|云端|同步|保存/.test(item)) ?? "按已确认 PRD 保存完成核心任务所需的最少数据";
  const permissionSummary = isTimer
    ? "页面和声音提醒默认可用；浏览器系统通知会先请求用户授权，拒绝后不影响计时。"
    : assumptions.find((item) => /通知|声音|权限|允许/.test(item)) ?? accounts[0] ?? "当前没有额外账号或授权要求";

  function chooseUiStyle(value: UiStyleKey) {
    setUiStyleKey(value);
    saveUiStylePreference(projectId, value);
  }

  function goToFrame(index: number) {
    const safeIndex = (index + frames.length) % frames.length;
    setActiveIndex(safeIndex);
  }

  return (
    <div className="solution-visual-view">
      <section className="solution-visual-baseline">
        <span><CircleCheckBig size={18} /></span>
        <div><small>根据已确认 PRD 生成</small><strong>{prdTitle}</strong><p>先用低保真界面把关键体验走一遍；这里只确认结构、状态和交互，不代表最终视觉稿。</p></div>
        <em>低保真方案</em>
      </section>

      <section className="solution-storyboard" aria-labelledby="solution-storyboard-title">
        <header className="solution-storyboard-heading">
          <div><span>可点击界面故事板</span><h2 id="solution-storyboard-title">像用户一样，把产品先走一遍</h2><p>点击下方界面缩略图，或直接点击线框图里的主按钮，查看操作后会发生什么。</p></div>
          <div className="storyboard-pager"><button type="button" onClick={() => goToFrame(activeIndex - 1)} aria-label="上一个界面"><ArrowLeft size={16} /></button><span>{activeIndex + 1} / {frames.length}</span><button type="button" onClick={() => goToFrame(activeIndex + 1)} aria-label="下一个界面"><ArrowRight size={16} /></button></div>
        </header>

        <div className="solution-storyboard-stage">
          <div className="solution-browser-frame">
            <div className="solution-browser-bar"><span><i /><i /><i /></span><small>{prdTitle} · 低保真预览</small><em>可点击</em></div>
            {isTimer
              ? <TimerWireframe frame={active} onAdvance={() => goToFrame(activeIndex + 1)} />
              : <GenericWireframe frame={active} productTitle={prdTitle} onAdvance={() => goToFrame(activeIndex + 1)} />}
          </div>

          <aside className="solution-frame-inspector">
            <span>{active.eyebrow}</span>
            <h3>{active.title}</h3>
            <p>{active.description}</p>
            <dl>
              <div><dt>用户现在看到</dt><dd>{active.title}</dd></div>
              <div><dt>点击“{active.action}”后</dt><dd>{active.result}</dd></div>
              <div><dt>这一屏确认什么</dt><dd>信息是否够用、主操作是否明确、前后状态是否连贯</dd></div>
            </dl>
            <button type="button" onClick={() => goToFrame(activeIndex + 1)}>体验下一界面<ArrowRight size={15} /></button>
          </aside>
        </div>

        <div className="solution-frame-strip" role="tablist" aria-label="关键界面">
          {frames.map((frame, index) => (
            <button key={frame.key} type="button" role="tab" aria-selected={index === activeIndex} className={index === activeIndex ? "active" : ""} onClick={() => setActiveIndex(index)}>
              <span className="mini-wireframe"><i /><i /><i /><b /></span>
              <small>界面 {index + 1}</small><strong>{frame.title}</strong>
            </button>
          ))}
        </div>
      </section>

      <section className="solution-decision-summary" aria-label="方案确认摘要">
        <div className="solution-scope-column included"><header><Check size={17} /><div><small>这次会生成</small><h3>首版范围</h3></div></header><ul>{(included.length > 0 ? included : ["完成 PRD 中的核心使用流程"]).map((item) => <li key={item}>{item}</li>)}</ul></div>
        <div className="solution-scope-column excluded"><header><Clock3 size={17} /><div><small>避免首版过重</small><h3>以后再做</h3></div></header><ul>{(excluded.length > 0 ? excluded : ["PRD 未确认的扩展能力"]).map((item) => <li key={item}>{item}</li>)}</ul></div>
        <div className="solution-scope-column pending"><header><BellRing size={17} /><div><small>生成前最后核对</small><h3>待确认事项</h3></div></header><ul>{(risks.length > 0 ? risks : ["当前没有阻碍生成的待确认事项"]).map((item) => <li key={item}>{item}</li>)}</ul></div>
      </section>

      <section className="solution-backend-contract" aria-labelledby="solution-backend-title">
        <header><div><span>真实生成与后端保障</span><h2 id="solution-backend-title">确认后，系统会怎样把方案变成网页</h2></div><em><ShieldCheck size={14} />后端已接入生成流程</em></header>
        <div>
          <article><span><Code2 size={17} /></span><strong>生成真实 HTML</strong><p>生成后端读取 PRD、完整文档、当前方案和 UI 风格，输出项目独立的 <code>web/index.html</code>。</p></article>
          <article><span><Database size={17} /></span><strong>状态与数据</strong><p>{isTimer ? "计时使用时间戳恢复，暂停、继续和刷新后的状态保持一致。" : dataSummary}</p></article>
          <article><span><BellRing size={17} /></span><strong>权限与提醒</strong><p>{permissionSummary}</p></article>
          <article><span><ShieldCheck size={17} /></span><strong>检查与可恢复</strong><p>生成后会检查文件、核心交互和预览；版本保存在项目工作区，失败可从安全检查点继续。</p></article>
        </div>
      </section>

      <UiStylePicker value={uiStyleKey} onChange={chooseUiStyle} />
    </div>
  );
}
