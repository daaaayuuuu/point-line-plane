export const DEPLOYMENT_SKILL_STEPS = [
  { id: "baseline", title: "检查上线准备", stepIds: ["account", "identity", "access", "mvp", "inspect"] },
  { id: "plan", title: "看懂方案费用", stepIds: ["permissions", "gateway"] },
  { id: "authorization", title: "确认操作权限", stepIds: ["operation_review"] },
  { id: "production", title: "准备线上版本", stepIds: ["online_code", "tools", "environment", "auth", "persistence", "storage", "reserved"] },
  { id: "publish", title: "发布你的产品", stepIds: ["backend", "frontend"] },
  { id: "verification", title: "检查实际使用效果", stepIds: ["address", "monitor"] },
  { id: "delivery", title: "领取网址和使用说明", stepIds: ["acceptance"] },
] as const;

/** Keep project-wide deployment records separate from the active guide. */
export function deploymentGuideView(route: string | null, stepId: string, hasCredential: boolean, hasDeployment: boolean) {
  const result = Boolean(route && hasDeployment && ["backend", "frontend", "address", "acceptance", "monitor"].includes(stepId));
  return {
    onboarding: !route ? hasCredential ? "resume" : "choose" : null,
    result,
    history: hasDeployment && !result,
    gateway: Boolean(route && stepId === "gateway"),
  };
}

export function usableDeploymentAuthorization(authorization: {status: string; expires_at: string} | null, now: number) {
  return Boolean(authorization && ["pending", "confirmed"].includes(authorization.status) && Date.parse(authorization.expires_at) > now);
}

/** Navigation belongs to the current conversation, not the project's old releases. */
export function deploymentNavigationProgress(started: boolean, workflowIndex: number, published: boolean, finished: boolean) {
  if (!started) return { enabled: false, completedThrough: -1, unlockedThrough: -1 };
  const reached = finished ? 6 : published && workflowIndex >= 4 ? Math.max(5, workflowIndex) : workflowIndex;
  return { enabled: true, completedThrough: finished ? 6 : reached - 1, unlockedThrough: reached };
}
