"use client";

import type { ProjectDetail } from "@/lib/api/types";
import { PRODUCT_PHASES, type ProductPhaseKey, type StageKey } from "./data";
import { PhaseHeadingProvider } from "./StageUi";
import { M1ARequirements } from "./stages/M1ARequirements";
import { M1DPreview } from "./stages/M1DPreview";
import { M2AUsage } from "./stages/M2AUsage";
import { M2BDeployment } from "./stages/M2BDeployment";
import { M2CDelivery } from "./stages/M2CDelivery";
import { M3M4Operations } from "./stages/M3M4Operations";

export type StageProps = {
  project: ProjectDetail;
  onProjectChange: (project: ProjectDetail) => void;
  onRefresh: () => Promise<void>;
  onError: (error: unknown) => void;
  onNotice: (message: string) => void;
  onNavigate: (stage: StageKey) => void;
};

const PHASE_VIEWS: Partial<Record<ProductPhaseKey, Array<{ key: StageKey; label: string }>>> = {
  launch: [
    { key: "m2b", label: "发布产品" },
    { key: "m2c", label: "交付内容" },
  ],
};

export function StagePanel({ phase, stage, onSelectStage, ...props }: StageProps & {
  phase: ProductPhaseKey;
  stage: StageKey;
  onSelectStage: (stage: StageKey) => void;
}) {
  const panels: Record<StageKey, React.ReactNode> = {
    m1a: <M1ARequirements key={props.project.id} {...props} focus={phase === "solution" ? "solution" : "idea"} />,
    m1b: <M1ARequirements key={`${props.project.id}-visual-solution`} {...props} focus="solution" />,
    m1c: <M1DPreview key={`${props.project.id}-build-preview`} {...props} />,
    m1d: <M1DPreview key={`${props.project.id}-build-preview-legacy`} {...props} />,
    m2a: <M2AUsage {...props} />,
    m2b: <M2BDeployment {...props} />,
    m2c: <M2CDelivery {...props} />,
    m3m4: <M3M4Operations {...props} />,
  };
  const views = PHASE_VIEWS[phase] ?? [];
  const phaseIndex = PRODUCT_PHASES.findIndex((item) => item.key === phase);
  const phaseHeading = PRODUCT_PHASES[phaseIndex] ?? PRODUCT_PHASES[0];
  const isCodexWorkbench = phase === "idea" && stage === "m1a";
  return (
    <div className={`stage-canvas ${isCodexWorkbench ? "codex-stage-canvas" : ""}`}>
      {views.length > 0 && (
        <nav className="phase-view-tabs" aria-label="本阶段内容">
          {views.map((view) => (
            <button key={view.key} type="button" className={stage === view.key ? "active" : ""} onClick={() => onSelectStage(view.key)} aria-current={stage === view.key ? "page" : undefined}>
              {view.label}
            </button>
          ))}
        </nav>
      )}
      <PhaseHeadingProvider heading={{ step: phaseIndex + 1, total: PRODUCT_PHASES.length, title: phaseHeading.shortTitle, description: phaseHeading.description }}>
        {panels[stage]}
      </PhaseHeadingProvider>
    </div>
  );
}
