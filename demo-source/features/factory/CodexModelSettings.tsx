"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { ArrowLeft, Check, ChevronDown, ChevronRight, RotateCcw, Zap } from "lucide-react";
import { CODEX_MODELS, CODEX_EFFORTS, codexEffortsForModel } from "@/lib/codex-models";

type Effort = (typeof CODEX_EFFORTS)[number];
type Props = {
  fastMode: boolean;
  onFastModeChange: (enabled: boolean) => void;
  model: string;
  effort: Effort;
  onModelChange: (model: string) => void;
  onEffortChange: (effort: Effort) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  disabled?: boolean;
};

export function CodexModelSettings({ fastMode, onFastModeChange, model, effort, onModelChange, onEffortChange, open, onOpenChange, disabled }: Props) {
  const [showModels, setShowModels] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const efforts = codexEffortsForModel(model);
  const index = Math.max(0, efforts.indexOf(effort));
  const percent = index / (efforts.length - 1) * 100;
  const modelLabel = `GPT-${model.replace("6.0 Astra", "6 Astra")}`;

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) onOpenChange(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { onOpenChange(false); trigger.current?.focus(); }
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [open, onOpenChange]);

  return (
    <div ref={root} className="codex-settings-anchor">
      <button ref={trigger} className="codex-model-trigger" type="button" aria-label="模型和推理设置" aria-expanded={open} aria-haspopup="dialog" disabled={disabled} onClick={() => { setShowModels(false); onOpenChange(!open); }}>
        <span>{model.replace("6.0 Astra", "6 Astra")}</span><small>{effort}</small>{fastMode && <small className="codex-speed-badge"><Zap size={13} />1.5×</small>}<ChevronDown size={15} />
      </button>
      {open && <div className="codex-reasoning-card" role="dialog" aria-label="模型和推理设置">
        {showModels ? <>
          <div className="codex-settings-model-heading"><button type="button" className="codex-settings-icon" aria-label="返回推理设置" onClick={() => setShowModels(false)}><ArrowLeft size={18} /></button><span>选择模型</span></div>
          <div className="codex-settings-model-list" role="menu" aria-label="选择模型">
            {CODEX_MODELS.map((item) => <button type="button" role="menuitemradio" aria-checked={model === item.id} className="codex-model-choice codex-model-choice-detail" key={item.id} onClick={() => {
              onModelChange(item.id);
              if (!codexEffortsForModel(item.id).includes(effort)) onEffortChange("中");
              setShowModels(false);
            }}><span><strong>GPT-{item.id.replace("6.0 Astra", "6 Astra")}</strong><small>{item.description}</small></span>{model === item.id && <Check size={16} />}</button>)}
          </div>
        </> : <>
          <div className="codex-reasoning-top">
            <button type="button" className={`codex-settings-icon ${fastMode ? "is-active" : ""}`} aria-label="1.5倍加速" aria-pressed={fastMode} title="1.5× 加速模式，实际速度取决于模型和服务负载" onClick={() => onFastModeChange(!fastMode)}><Zap size={19} /></button>
            <button type="button" className="codex-reasoning-summary" aria-label="切换模型" onClick={() => setShowModels(true)}><span className="codex-reasoning-current">{effort}<ChevronRight size={17} /></span><span className="codex-reasoning-model">{modelLabel}</span></button>
            <button type="button" className="codex-settings-icon" aria-label="重置推理强度为中" title="重置为中等推理强度" onClick={() => onEffortChange("中")}><RotateCcw size={19} /></button>
          </div>
          <div className="codex-reasoning-slider" style={{ "--reasoning-progress": `${percent}%` } as CSSProperties}>
            <div className="codex-reasoning-track" />
            <div className="codex-reasoning-dots" aria-hidden="true">{efforts.map((item, i) => <span className={i <= index ? "is-filled" : ""} key={item} />)}</div>
            <input type="range" min={0} max={efforts.length - 1} step={1} value={index} aria-label="推理强度" aria-valuetext={effort} onChange={(event) => onEffortChange(efforts[Number(event.currentTarget.value)])} />
          </div>
        </>}
      </div>}
    </div>
  );
}
