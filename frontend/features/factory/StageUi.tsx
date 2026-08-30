import { createContext, useContext, type ReactNode } from "react";
import { ArrowRight, Check, CircleAlert, LockKeyhole, Sparkles } from "lucide-react";
import { statusText } from "./data";

type PhaseHeading = {
  step: number;
  total: number;
  title: string;
  description: string;
};

const PhaseHeadingContext = createContext<PhaseHeading | null>(null);

export function PhaseHeadingProvider({ heading, children }: { heading: PhaseHeading; children: ReactNode }) {
  return <PhaseHeadingContext.Provider value={heading}>{children}</PhaseHeadingContext.Provider>;
}

export function StageIntro({ eyebrow, title, description, aside }: {
  eyebrow: string;
  title: string;
  description: string;
  aside?: ReactNode;
}) {
  const phaseHeading = useContext(PhaseHeadingContext);
  return (
    <header className="stage-intro">
      <div>
        {!phaseHeading && <span className="eyebrow">{eyebrow}</span>}
        <h1>{phaseHeading?.title ?? title}</h1>
        <p>{phaseHeading?.description ?? description}</p>
      </div>
      {aside}
    </header>
  );
}

export function Panel({ children, className = "", title, action }: {
  children: ReactNode;
  className?: string;
  title?: string;
  action?: ReactNode;
}) {
  return (
    <section className={`surface-card ${className}`}>
      {(title || action) && <div className="surface-heading">{title && <h2>{title}</h2>}{action}</div>}
      {children}
    </section>
  );
}

export function StatusPill({ status }: { status?: string | null }) {
  const value = status?.toLowerCase() ?? "idle";
  const tone = ["succeeded", "passed", "ready", "verified", "active", "confirmed"].includes(value)
    ? "success"
    : ["failed", "blocked", "paused", "invalid"].includes(value)
      ? "danger"
      : ["running", "queued", "provisioning", "open"].includes(value)
        ? "progress"
        : "neutral";
  return <span className={`status-pill ${tone}`}><i />{statusText(value)}</span>;
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <div className="empty-panel"><span><Sparkles size={21} /></span><strong>{title}</strong><p>{description}</p>{action}</div>
  );
}

export function LockedState({ title, description, actionLabel, onAction }: {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="locked-panel"><span><LockKeyhole size={20} /></span><div><strong>{title}</strong><p>{description}</p></div>{actionLabel && onAction && <button className="ghost-button" type="button" onClick={onAction}>{actionLabel}<ArrowRight size={15} /></button>}</div>
  );
}

export function CheckItem({ done, children }: { done: boolean; children: ReactNode }) {
  return <li className={done ? "done" : ""}><span>{done ? <Check size={14} /> : <CircleAlert size={14} />}</span>{children}</li>;
}

export function KeyValue({ label, value }: { label: string; value: ReactNode }) {
  return <div className="key-value"><span>{label}</span><strong>{value}</strong></div>;
}

export function ObjectList({ value }: { value: Record<string, unknown> }) {
  const entries = Object.entries(value).filter(([key, item]) => item !== null && item !== "" && key !== "generation");
  const implementationEntries = entries.filter(([key]) => ["architecture", "technical_contract"].includes(key));
  const productEntries = entries.filter(([key]) => !["architecture", "technical_contract"].includes(key));
  if (productEntries.length === 0 && implementationEntries.length === 0) return <p className="muted-copy">暂无可展示内容。</p>;
  return (
    <>
      <dl className="object-list">
        {productEntries.slice(0, 12).map(([key, item]) => (
          <div key={key}><dt>{humanize(key)}</dt><dd>{productFacingValue(key, item)}</dd></div>
        ))}
      </dl>
      {implementationEntries.length > 0 && (
        <details className="implementation-details">
          <summary><span>实现说明</span><small>给技术接手或排查问题时查看</small></summary>
          <dl className="object-list technical-object-list">
            {implementationEntries.map(([key, item]) => (
              <div key={key}><dt>{humanize(key)}</dt><dd>{stringify(item)}</dd></div>
            ))}
          </dl>
        </details>
      )}
    </>
  );
}

export function humanize(value: string): string {
  const known: Record<string, string> = {
    title: "标题", summary: "产品摘要", target_users: "目标用户", problem: "核心问题",
    core_flow: "核心使用流程", features: "主要功能", assumptions: "当前假设", source_notes: "需求来源",
    goals: "产品目标", scope: "首版范围", included: "本期包含", excluded: "暂不包含",
    risks: "主要风险", acceptance_criteria: "完成标准", recommended_approach: "推荐实现方式",
    product_scope: "产品范围", deferred: "后续能力", user_costs: "费用说明",
    external_accounts: "需要的账号或授权", deliverables: "交付内容", architecture: "技术实现结构",
    revision_notes: "修改记录", total: "总数", users: "用户", projects: "项目",
    tasks: "任务", deployments: "部署", status: "状态", provider: "服务商",
    item: "项目", estimate: "费用", note: "说明",
  };
  return known[value] ?? value.replaceAll("_", " ");
}

export function stringify(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => stringify(item)).join("；");
  if (typeof value === "object" && value !== null) return Object.entries(value as Record<string, unknown>).map(([key, item]) => `${humanize(key)}：${stringify(item)}`).join("；");
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value)
    .replaceAll("M1 mock", "首版体验")
    .replaceAll("mock", "体验环境")
    .replaceAll("Key", "服务授权")
    .replaceAll("Token", "使用记录")
    .replaceAll("Git", "保存版本");
}

function productFacingValue(key: string, value: unknown): string {
  if (key === "recommended_approach" && typeof value === "string") {
    return "采用一套便于快速上线、后续可扩展的整体方案。产品界面、业务处理、数据保存和 AI 服务彼此分工，具体技术实现由工厂负责。";
  }
  return stringify(value);
}
