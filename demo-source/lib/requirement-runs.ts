import { api } from "./api/client";
import type { CodexRequirementResponse } from "./api/types";

// Requests belong to conversations, not to the currently mounted stage panel.
export type RequirementRun = {
  controller: AbortController;
  message: string;
  startedAt: number;
  summary: string;
  reply: string;
  response?: CodexRequirementResponse;
  error?: unknown;
  settled: boolean;
};
const runs = new Map<string, RequirementRun>();
const key = (projectId: string, conversationId: string) => `${projectId}:${conversationId}`;
export function getRequirementRun(projectId: string, conversationId: string) {
  return runs.get(key(projectId, conversationId));
}
export function clearRequirementRun(projectId: string, conversationId: string) {
  runs.delete(key(projectId, conversationId));
}
export function startRequirementRun(
  projectId: string, conversationId: string, message: string,
  preferences: { model?: string; reasoningEffort?: string; serviceTier?: "fast" | "default" },
) {
  const existing = getRequirementRun(projectId, conversationId);
  if (existing) return existing;
  const run: RequirementRun = {
    message, controller: new AbortController(), startedAt: Date.now(), summary: "", reply: "", settled: false,
  };
  runs.set(key(projectId, conversationId), run);
  void api.sendCodexMessage(projectId, message, run.controller.signal,
    (summary) => { run.summary = summary; }, preferences,
    (reply) => { run.reply = reply; },
  ).then((response) => { run.response = response; })
    .catch((error: unknown) => { run.error = error; })
    .finally(() => { run.settled = true; });
  return run;
}
