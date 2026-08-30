import type {
  AppError,
  Artifact,
  Backup,
  BetaInvite,
  CloudCredential,
  CodexConversationListResponse,
  CodexConversationResponse,
  CodexLoginResult,
  CodexReasoningProgress,
  CodexRequirementResponse,
  DecisionCenter,
  DeliveryPackage,
  Deployment,
  DeploymentAuthorization,
  DevelopmentRun,
  DevelopmentWorkspace,
  Finding,
  GithubSync,
  ModelCredential,
  OperationsMetrics,
  PlatformCapabilities,
  Preview,
  PreviewRun,
  ProductDashboard,
  ProductGraph,
  ProjectDetail,
  ProjectSummary,
  QualityHistory,
  Quota,
  RequirementResponse,
  Simulation,
  Task,
  UsageLedger,
  UsageSummary,
  User,
} from "./types";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8018/api/v1").replace(/\/$/, "");

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  operationsToken?: string;
};

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function normalizeError(status: number, payload: unknown): AppError {
  const error = isObject(payload) && isObject(payload.error) ? payload.error : payload;
  const code = isObject(error) && typeof error.code === "string" ? error.code : `HTTP_${status}`;
  const message = isObject(error) && typeof error.message === "string"
    ? error.message
    : "服务暂时无法完成这个操作。";
  const requestId = isObject(error) && typeof error.trace_id === "string" ? error.trace_id : undefined;
  return {
    code,
    message,
    userMessage: message,
    retryable: status >= 500 || status === 408 || status === 429,
    requestId,
    status,
  };
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body !== undefined && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (options.operationsToken) headers.set("X-Operations-Token", options.operationsToken);
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: "include",
    body: options.body === undefined
      ? undefined
      : options.body instanceof FormData
        ? options.body
        : JSON.stringify(options.body),
  });
  const contentType = response.headers.get("content-type") ?? "";
  const payload: unknown = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) throw normalizeError(response.status, payload);
  return payload as T;
}

export function isAppError(value: unknown): value is AppError {
  return isObject(value) && typeof value.code === "string" && typeof value.userMessage === "string";
}

async function sendCodexMessageWithReasoning(
  projectId: string,
  message: string,
  signal?: AbortSignal,
  onReasoningSummary?: (summary: string) => void,
  preferences?: { model?: string; reasoningEffort?: string },
): Promise<CodexRequirementResponse> {
  const body = {
    message,
    question_id: null,
    model: preferences?.model,
    reasoning_effort: preferences?.reasoningEffort,
  };
  if (!onReasoningSummary) {
    return request<CodexRequirementResponse>(`/projects/${projectId}/codex/messages`, {
      method: "POST",
      body,
      signal,
    });
  }

  const progressId = crypto.randomUUID();
  let polling = false;
  const poll = async () => {
    if (polling || signal?.aborted) return;
    polling = true;
    try {
      const progress = await request<CodexReasoningProgress>(
        `/projects/${projectId}/codex/reasoning/${progressId}`,
        { signal },
      );
      if (progress.summary) onReasoningSummary(progress.summary);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        // Reasoning progress is supplementary; the main Codex response remains authoritative.
      }
    } finally {
      polling = false;
    }
  };
  const timer = globalThis.setInterval(() => { void poll(); }, 750);
  void poll();
  try {
    const response = await request<CodexRequirementResponse>(
      `/projects/${projectId}/codex/messages`,
      {
        method: "POST",
        body: { ...body, progress_id: progressId },
        signal,
      },
    );
    await poll();
    return response;
  } finally {
    globalThis.clearInterval(timer);
  }
}

export const api = {
  baseUrl: API_BASE,
  health: () => request<Record<string, string>>("/health"),
  capabilities: () => request<PlatformCapabilities>("/capabilities"),
  me: () => request<{ user: User }>("/auth/me"),
  startCodexLogin: () =>
    request<CodexLoginResult>("/auth/codex/start", { method: "POST" }),
  codexLoginStatus: (attemptId: string) =>
    request<CodexLoginResult>(`/auth/codex/status?attempt_id=${encodeURIComponent(attemptId)}`),
  login: (inviteCode: string, displayName: string) =>
    request<{ user: User }>("/auth/invite-login", {
      method: "POST",
      body: { invite_code: inviteCode, display_name: displayName },
    }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),

  projects: () => request<{ items: ProjectSummary[] }>("/projects"),
  project: (id: string) => request<ProjectDetail>(`/projects/${id}`),
  createProject: (name: string, idea: string) =>
    request<ProjectDetail>("/projects", { method: "POST", body: { name, idea } }),
  deleteProject: (id: string) =>
    request<{ ok: boolean }>(`/projects/${id}`, { method: "DELETE" }),
  codexConversation: (projectId: string) =>
    request<CodexConversationResponse>(`/projects/${projectId}/codex/conversation`),
  codexConversations: (projectId: string) =>
    request<CodexConversationListResponse>(`/projects/${projectId}/codex/conversations`),
  createCodexConversation: (projectId: string) =>
    request<CodexConversationResponse>(`/projects/${projectId}/codex/conversations`, { method: "POST" }),
  activateCodexConversation: (projectId: string, conversationId: string) =>
    request<CodexConversationResponse>(`/projects/${projectId}/codex/conversations/${conversationId}/activate`, { method: "POST" }),
  sendCodexMessage: (
    projectId: string,
    message: string,
    signal?: AbortSignal,
    onReasoningSummary?: (summary: string) => void,
    preferences?: { model?: string; reasoningEffort?: string },
  ) => sendCodexMessageWithReasoning(projectId, message, signal, onReasoningSummary, preferences),
  answerRequirement: (projectId: string, message: string, questionId?: string) =>
    request<RequirementResponse>(`/projects/${projectId}/requirements/messages`, {
      method: "POST",
      body: { message, question_id: questionId ?? null },
    }),
  uploadRequirement: (projectId: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<RequirementResponse>(`/projects/${projectId}/requirements/upload`, {
      method: "POST",
      body,
    });
  },
  artifacts: (projectId: string) =>
    request<{ items: Artifact[] }>(`/projects/${projectId}/artifacts`),
  confirmArtifact: (projectId: string, type: "prd" | "solution", artifactId: string, decision: "confirm" | "revise", comment?: string) =>
    request<{ project: ProjectDetail; artifact: Artifact; next_artifact?: Artifact | null }>(`/projects/${projectId}/confirmations/${type}`, {
      method: "POST",
      body: { artifact_id: artifactId, decision, comment: comment || null },
    }),

  initializeGraph: (projectId: string) =>
    request<ProductGraph>(`/projects/${projectId}/product-graph/initialize`, { method: "POST" }),
  productDashboard: (projectId: string) =>
    request<ProductDashboard>(`/projects/${projectId}/product-dashboard`),
  decisionCenter: (projectId: string) =>
    request<DecisionCenter>(`/projects/${projectId}/decision-center`),
  confirmDecision: (decisionId: string, optionKey: string) =>
    request<{ next_action: { code: string; message: string } }>(`/decisions/${decisionId}/confirm`, {
      method: "POST",
      body: { option_key: optionKey, idempotency_key: crypto.randomUUID() },
    }),
  startSimulation: (graphId: string) =>
    request<Simulation>(`/product-graphs/${graphId}/simulations`, {
      method: "POST",
      body: { persona_key: "first_time_non_technical_user", idempotency_key: crypto.randomUUID() },
    }),
  advanceSimulation: (runId: string) =>
    request<Simulation>(`/simulations/${runId}/advance`, { method: "POST" }),
  resolveFinding: (findingId: string, resolutionKey: "add_input_example" | "explain_before_input") =>
    request<{ finding: Finding; simulation: Simulation }>(`/findings/${findingId}/resolve`, {
      method: "POST",
      body: { resolution_key: resolutionKey, idempotency_key: crypto.randomUUID() },
    }),

  startDevelopment: (projectId: string, uiStyleKey: string) =>
    request<Task>(`/projects/${projectId}/development/start`, {
      method: "POST",
      body: { ui_style_key: uiStyleKey },
    }),
  task: (taskId: string) => request<Task>(`/tasks/${taskId}`),
  retryTask: (taskId: string) => request<Task>(`/tasks/${taskId}/retry`, { method: "POST" }),
  workspace: (projectId: string) =>
    request<DevelopmentWorkspace>(`/projects/${projectId}/development-workspace`),
  developmentRuns: (projectId: string) =>
    request<{ items: DevelopmentRun[] }>(`/projects/${projectId}/development-runs`),
  qualityHistory: (projectId: string) =>
    request<QualityHistory>(`/projects/${projectId}/quality-history`),

  preview: (token: string) => request<Preview>(`/previews/${token}`),
  runPreview: (token: string, input: string) =>
    request<PreviewRun>(`/previews/${token}/runs`, { method: "POST", body: { input } }),
  acceptPreview: (token: string, checklist: Record<string, boolean>) =>
    request<{ decision: string }>(`/previews/${token}/acceptance`, {
      method: "POST",
      body: checklist,
    }),
  previewFeedback: (projectId: string, feedback: string) =>
    request<{ classification: string; reason: string; next_stage: string; project: ProjectDetail }>(`/projects/${projectId}/preview-feedback`, {
      method: "POST",
      body: { feedback },
    }),

  usageSummary: () => request<UsageSummary>("/usage/summary"),
  quota: () => request<Quota>("/usage/quota"),
  usageLedger: (projectId?: string) =>
    request<{ items: UsageLedger[] }>(`/usage/ledger${projectId ? `?project_id=${projectId}` : ""}`),
  modelCredentials: () => request<{ items: ModelCredential[] }>("/model-credentials"),
  connectModelCredential: (apiKey: string, projectId: string, scope: string) =>
    request<ModelCredential>("/model-credentials", {
      method: "POST",
      body: { provider: "openai_compatible", api_key: apiKey, project_id: projectId, scope },
    }),
  verifyModelCredential: (id: string) =>
    request<ModelCredential>(`/model-credentials/${id}/verify`, {
      method: "POST",
      body: { confirm_test_charge: true },
    }),
  revokeModelCredential: (id: string) =>
    request<{ ok: boolean }>(`/model-credentials/${id}/revoke`, {
      method: "POST",
      body: { confirm: true },
    }),

  connectCloudCredential: (projectId: string, accessKeyId: string, secretAccessKey: string) =>
    request<CloudCredential>("/cloud-credentials", {
      method: "POST",
      body: {
        provider: "volcano_engine",
        project_id: projectId,
        access_key_id: accessKeyId,
        secret_access_key: secretAccessKey,
      },
    }),
  cloudCredentials: (projectId: string) =>
    request<{ items: CloudCredential[] }>(`/cloud-credentials?project_id=${encodeURIComponent(projectId)}`),
  deploymentAuthorizations: (projectId: string) =>
    request<{ items: DeploymentAuthorization[] }>(`/projects/${projectId}/deployment-authorizations`),
  quoteDeployment: (projectId: string, credentialId: string, region = "cn-beijing") =>
    request<DeploymentAuthorization>(`/projects/${projectId}/deployment-authorizations`, {
      method: "POST",
      body: { credential_id: credentialId, action: "deploy", region, environment: "production" },
    }),
  confirmDeployment: (authorizationId: string) =>
    request<DeploymentAuthorization>(`/deployment-authorizations/${authorizationId}/confirm`, {
      method: "POST",
      body: { confirm: true },
    }),
  startDeployment: (projectId: string, authorizationId: string) =>
    request<Deployment>(`/projects/${projectId}/deployments`, {
      method: "POST",
      body: { authorization_id: authorizationId },
    }),
  deployments: (projectId: string) =>
    request<{ items: Deployment[] }>(`/projects/${projectId}/deployments`),

  createDeliveryPackage: (projectId: string, deploymentId: string) =>
    request<DeliveryPackage>(`/projects/${projectId}/delivery-packages`, {
      method: "POST",
      body: { deployment_id: deploymentId, confirm: true },
    }),
  deliveryPackages: (projectId: string) =>
    request<{ items: DeliveryPackage[] }>(`/projects/${projectId}/delivery-packages`),
  syncGithub: (packageId: string, repositoryFullName: string) =>
    request<GithubSync>(`/delivery-packages/${packageId}/github-sync`, {
      method: "POST",
      body: { repository_full_name: repositoryFullName, branch: "main", confirm: true },
    }),
  downloadUrl: (packageId: string) => `${API_BASE}/delivery-packages/${packageId}/download`,

  operationsMetrics: (token: string) =>
    request<OperationsMetrics>("/operations/metrics", { operationsToken: token }),
  betaInvites: (token: string) =>
    request<BetaInvite[]>("/operations/beta-invites", { operationsToken: token }),
  createBetaInvite: (token: string, code: string, label: string) =>
    request<BetaInvite>("/operations/beta-invites", {
      method: "POST",
      operationsToken: token,
      body: { code, label, max_uses: 1 },
    }),
  backups: (token: string) => request<Backup[]>("/operations/backups", { operationsToken: token }),
  createBackup: (token: string) =>
    request<Backup>("/operations/backups", {
      method: "POST",
      operationsToken: token,
      body: { confirm: true },
    }),
};
