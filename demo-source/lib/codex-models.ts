// Model identifiers and reasoning levels supported by the local Codex bridge.
export const CODEX_MODELS = [
  { id: "6.0 Astra", effort: "中", description: "复杂任务、编程与深度推理" },
  { id: "5.6 Sol", effort: "中", description: "复杂产品任务与深度推理" },
  { id: "5.6 Terra", effort: "高", description: "日常产品工作与快速迭代" },
  { id: "5.6 Luna", effort: "中", description: "轻量任务与快速响应" },
  { id: "5.5", effort: "高", description: "稳定通用的助手" },
] as const;
export const CODEX_EFFORTS = ["低", "中", "高", "极高", "最高", "超强"] as const;
export const CODEX_MODEL_IDS: Record<string, string> = {
  "6.0 Astra": "gpt-6-astra",
  "5.6 Sol": "gpt-5.6-sol",
  "5.6 Terra": "gpt-5.6-terra",
  "5.6 Luna": "gpt-5.6-luna",
  "5.5": "gpt-5.5",
};
export const CODEX_REASONING_EFFORT_IDS: Record<(typeof CODEX_EFFORTS)[number], string> = {
  低: "low", 中: "medium", 高: "high", 极高: "xhigh", 最高: "max", 超强: "ultra",
};
export function codexEffortsForModel(model: string) {
  return CODEX_EFFORTS.filter((effort) =>
    model === "5.5" ? effort !== "最高" && effort !== "超强" :
      model === "5.6 Luna" ? effort !== "超强" : true,
  );
}
