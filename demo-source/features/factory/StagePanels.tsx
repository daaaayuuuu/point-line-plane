"use client";

import type { ProjectDetail } from "@/lib/api/types";
import { PRODUCT_PHASES, type ProductPhaseKey, type StageKey } from "./data";
import { PhaseHeadingProvider } from "./StageUi";
import { M1ARequirements } from "./stages/M1ARequirements";
import { M1DPreview } from "./stages/M1DPreview";
import { M2AUsage } from "./stages/M2AUsage";
import { M2BDeployment } from "./stages/M2BDeployment";
import { M3M4Operations } from "./stages/M3M4Operations";

export type StageProps = {
  project: ProjectDetail;
  onProjectChange: (project: ProjectDetail) => void;
  onRefresh: () => Promise<void>;
  onError: (error: unknown) => void;
  onNotice: (message: string) => void;
  onNavigate: (stage: StageKey) => void;
};

export function StagePanel({ phase, stage, ...props }: StageProps & {
  phase: ProductPhaseKey;
  stage: StageKey;
}) {
  const panels: Record<StageKey, React.ReactNode> = {
    m1a: <M1ARequirements key={props.project.id} {...props} focus={phase === "solution" ? "solution" : "idea"} />,
    m1b: <M1ARequirements key={`${props.project.id}-visual-solution`} {...props} focus="solution" />,
    m1c: <M1DPreview key={`${props.project.id}-build-preview`} {...props} />,
    m1d: <M1DPreview key={`${props.project.id}-build-preview-legacy`} {...props} />,
    m2a: <M2AUsage {...props} />,
    m2b: <M2BDeployment {...props} />,
    m2c: <M2BDeployment {...props} />,
    m3m4: <M3M4Operations {...props} />,
  };
  const phaseIndex = PRODUCT_PHASES.findIndex((item) => item.key === phase);
  const phaseHeading = PRODUCT_PHASES[phaseIndex] ?? PRODUCT_PHASES[0];
  const isCodexWorkbench = phase === "idea" && stage === "m1a";
  const isDeploymentWorkbench = phase === "launch";
  return (
    <div className={`stage-canvas ${isCodexWorkbench ? "codex-stage-canvas" : ""} ${isDeploymentWorkbench ? "deployment-stage-canvas" : ""}`}>
      <PhaseHeadingProvider heading={{ step: phaseIndex + 1, total: PRODUCT_PHASES.length, title: phaseHeading.shortTitle, description: phaseHeading.description }}>
        {panels[stage]}
      </PhaseHeadingProvider>
    </div>
  );
}
