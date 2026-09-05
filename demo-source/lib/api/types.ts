export type JsonObject = Record<string, unknown>;

export type LowFidelityPrototypeScreen = {
  key: string;
  surface: string;
  title: string;
  description: string;
  primary_action: string;
  resulting_state: string;
  confirmation: "已确认" | "待确认" | "PRD 约定";
  source_items: string[];
  functional_requirements: string[];
};

export type LowFidelityPrototypeContract = {
  schema_version: "low_fidelity_prototype_v1";
  source: "prd.full_document";
  source_document_title: string;
  merge_policy: "merge_user_interfaces_preserve_requirements";
  screens: LowFidelityPrototypeScreen[];
  coverage: {
    end_to_end_loop: string[];
    functional_requirements: string[];
  };
};

export type User = {
  id: string;
  display_name: string;
  quota: JsonObject;
  created_at: string;
};

export type CodexLoginResult = {
  attempt_id: string;
  status: "pending" | "authenticated" | "failed";
  auth_url: string | null;
  account: { email: string; plan_type: string | null; display_name: string | null } | null;
  error: string | null;
};

export type NextAction = {
  code: string;
  message: string;
  questions?: Question[];
};

export type Question = {
  id: string;
  label: string;
  reason: string;
  required: boolean;
};

export type Artifact = {
  id: string;
  project_id: string;
  type: "prd" | "solution" | "failure_report" | "change_request" | string;
  version: number;
  status: string;
  content: JsonObject;
  created_at: string;
};

export type Task = {
  id: string;
  project_id: string;
  stage: string;
  status: string;
  progress: number;
  attempts: number;
  max_attempts: number;
  checkpoint: JsonObject;
  trace_id: string;
  error_code: string | null;
  created_at: string;
  updated_at: string;
};

export type PreviewSummary = {
  id: string;
  token: string;
  status: string;
  url_path: string;
  code_version: number;
  expires_at: string;
};

export type ProjectSummary = {
  id: string;
  name: string;
  idea: string;
  stage: string;
  status: string;
  scope: string;
  current_artifact_version: number;
  task_status: string | null;
  task_progress: number | null;
  preview_token: string | null;
  created_at: string;
  updated_at: string;
};

export type ProjectDetail = ProjectSummary & {
  latest_artifacts?: Artifact[];
  confirmations?: Array<JsonObject>;
  active_task?: Task | null;
  preview?: PreviewSummary | null;
  preview_accepted?: boolean;
  production_prepared?: boolean;
  next_action: NextAction;
};

export type RequirementResponse = {
  project: ProjectDetail;
  status: "reply" | "question" | "prd_ready";
  reply: string;
  questions?: Question[];
  artifact?: Artifact | null;
};

export type CodexConversationMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
};

export type CodexClarifyingQuestion = {
  mode: "single" | "multiple";
  prompt: string;
  options: string[];
};

export type CodexConversationResponse = {
  project: ProjectDetail;
  conversation_id: string;
  title: string;
  thread_id: string | null;
  messages: CodexConversationMessage[];
  draft: JsonObject | null;
  current_question?: CodexClarifyingQuestion | null;
};

export type CodexConversationSummary = {
  id: string;
  title: string;
  active: boolean;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type CodexConversationListResponse = {
  items: CodexConversationSummary[];
};

export type CodexRequirementResponse = CodexConversationResponse & {
  status: "reply" | "question" | "prd_ready";
  reply: string;
  artifact?: Artifact | null;
};

export type CodexReasoningProgress = {
  status: "pending" | "running" | "completed" | "failed";
  summary: string;
  reply?: string;
};

export type ProductNode = {
  id: string;
  graph_id: string;
  key: string;
  position: number;
  node_type: string;
  status: string;
  title: string;
  caption: string;
  product_purpose: string;
  user_sees: string;
  system_does: string;
  technical_contract: JsonObject;
};

export type ProductGraph = {
  id: string;
  project_id: string;
  version: number;
  status: string;
  title: string;
  product_goal: string;
  source_artifact_id: string | null;
  base_code_version_id: string | null;
  nodes: ProductNode[];
  created_at: string;
  updated_at: string;
};

export type DecisionOption = {
  id: string;
  key: string;
  position: number;
  title: string;
  description: string;
  recommended: boolean;
  product_impact: JsonObject;
  technical_effects: JsonObject;
};

export type ProductDecision = {
  id: string;
  project_id: string;
  graph_id: string;
  node_id: string;
  key: string;
  status: string;
  title: string;
  question: string;
  selected_option_key: string | null;
  options: DecisionOption[];
  confirmed_at: string | null;
  created_at: string;
};

export type DecisionCenter = {
  project_id: string;
  graph_id: string;
  open_count: number;
  confirmed_count: number;
  items: ProductDecision[];
};

export type Finding = {
  id: string;
  run_id: string;
  node_id: string;
  node_key: string;
  severity: string;
  status: string;
  product_summary: string;
  evidence: JsonObject;
  resolution_key: string | null;
  resolution_options: JsonObject[];
  resolved_at: string | null;
  created_at: string;
};

export type Simulation = {
  id: string;
  project_id: string;
  graph_id: string;
  persona_key: string;
  persona_name: string;
  status: string;
  current_node_id: string | null;
  checkpoint: JsonObject;
  steps: Array<{
    id: string;
    node_id: string;
    node_key: string;
    node_title: string;
    sequence: number;
    status: string;
    observation: string;
    duration_ms: number;
  }>;
  findings: Finding[];
  started_at: string | null;
  completed_at: string | null;
};

export type ProductDashboard = {
  project_id: string;
  graph: ProductGraph;
  decision_center: DecisionCenter;
  latest_simulation: Simulation | null;
  open_findings: Finding[];
  queued_changes: JsonObject[];
  next_action: NextAction;
};

export type CodeFile = {
  id: string;
  path: string;
  language: string;
  product_purpose: string;
  sha256: string;
  size_bytes: number;
};

export type ToolExecution = {
  id: string;
  sequence: number;
  tool_name: string;
  side_effect: string;
  status: string;
  input_summary: JsonObject;
  output_summary: JsonObject;
  error_code: string | null;
  started_at: string;
  completed_at: string | null;
};

export type DevelopmentRun = {
  id: string;
  project_id: string;
  workspace_id: string;
  task_id: string;
  code_version_id: string | null;
  resumed_from_run_id: string | null;
  status: string;
  current_step: string;
  provider: string | null;
  model: string | null;
  provider_verification: string | null;
  plan: JsonObject;
  budget: JsonObject;
  context: JsonObject;
  usage: JsonObject;
  error_code: string | null;
  tools: ToolExecution[];
  files: CodeFile[];
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type DevelopmentWorkspace = {
  id: string;
  project_id: string;
  runtime_type: string;
  status: string;
  current_commit_ref: string | null;
  file_count: number;
  size_bytes: number;
  created_at: string;
  updated_at: string;
};

export type QualityRun = {
  id: string;
  kind: string;
  status: string;
  attempt: number;
  duration_ms: number;
  exit_code: number | null;
  summary: JsonObject;
  output_excerpt: string;
  started_at: string;
  completed_at: string | null;
};

export type QualityHistory = {
  quality_runs: QualityRun[];
  repair_attempts: Array<{
    id: string;
    attempt: number;
    status: string;
    strategy_summary: string;
    error_code: string | null;
  }>;
};

export type Preview = {
  id: string;
  token: string;
  project_id: string;
  status: string;
  url_path: string;
  expires_at: string;
  code_version: {
    id: string;
    version: number;
    commit_ref: string;
    test_status: string;
    manifest: JsonObject;
  };
  config: {
    title: string;
    description: string;
    input_label: string;
    input_placeholder: string;
    submit_label: string;
    output_title: string;
    template?: string;
  };
  history: PreviewRun[];
};

export type PreviewRun = {
  id: string;
  input: string;
  result: { summary: string; key_points: string[]; next_step: string };
  provider: string;
  model: string;
  provider_verification: string;
  usage: JsonObject;
  latency_ms: number;
  created_at: string;
};

export type Quota = {
  plan: string;
  granted_units: number;
  consumed_units: number;
  reserved_units: number;
  remaining_units: number;
};

export type UsageSummary = {
  quota: Quota;
  total_tokens: number;
  platform_quota_units: number;
  estimated_cost_microusd: number;
  pricing_configured: boolean;
};

export type UsageLedger = {
  id: string;
  operation: string;
  provider: string;
  model: string;
  source: string;
  total_tokens: number;
  quota_units: number;
  estimated_cost_microusd: number;
  pricing_configured: boolean;
  status: string;
  trace_id: string;
  created_at: string;
};

export type ModelCredential = {
  id: string;
  project_id: string | null;
  provider: string;
  model: string;
  scope: string;
  masked_hint: string;
  status: string;
  expires_at: string | null;
  verified_at: string | null;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CloudCredential = {
  id: string;
  project_id: string;
  provider: string;
  service: string;
  scope: string;
  masked_access_key: string;
  status: string;
  expires_at: string | null;
  created_at: string;
};

export type PlatformCapabilities = {
  ai_provider_mode: "mock" | "unverified" | "verified";
  ai_provider: string;
  ai_model: string;
  generated_execution_mode: string;
  deployment_enabled: boolean;
  deployment_mode: "mock" | "external";
  deployment_provider: string;
  deployment_region: string;
  github_sync_mode: "mock" | "external";
};

export type CostAuthorization = {
  id: string;
  project_id: string;
  credential_ref_id: string | null;
  operation: string;
  provider: string;
  model: string;
  source: string;
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  estimated_quota_units: number;
  estimated_cost_microusd: number;
  pricing_configured: boolean;
  requires_confirmation: boolean;
  status: string;
  expires_at: string;
  confirmed_at: string | null;
  consumed_at: string | null;
  created_at: string;
};

export type DeploymentAuthorization = {
  id: string;
  project_id: string;
  credential_ref_id: string;
  action: string;
  provider: string;
  region: string;
  environment: string;
  permission_scope: JsonObject;
  estimated_cost: JsonObject;
  status: string;
  expires_at: string;
  confirmed_at?: string | null;
  consumed_at?: string | null;
  created_at?: string;
};

export type DeploymentAttachment = {
  filename: string;
  content_type: string;
  size_bytes: number;
  extracted_characters: number;
  stored: false;
  reply: string;
};

export type Deployment = {
  id: string;
  project_id: string;
  revision: number;
  kind: string;
  provider: string;
  region: string;
  environment: string;
  status: string;
  provider_ref?: string | null;
  deployment_url: string | null;
  checkpoint?: JsonObject;
  evidence?: JsonObject;
  attempts: number;
  error_code: string | null;
  trace_id: string;
  created_at: string;
  updated_at: string;
  events: Array<JsonObject>;
};

export type DeploymentAgentResponse = {
  project: ProjectDetail;
  conversation_id: string;
  thread_id: string;
  turn_id: string;
  reply: string;
  status: "guidance" | "blocked" | "needs_user_action" | "needs_confirmation" | "in_progress" | "succeeded" | "failed";
  action: "report_status" | "open_preview" | "connect_cloud" | "quote_deployment" | "request_deploy_confirmation" | "refresh_deployment" | "show_deployment_result" | "prepare_rollback" | "explain";
  selected_step_id: string | null;
  skill: {
    name: "vibe-deployment";
    source: string;
    mode: "real_guarded";
  };
  authorization: DeploymentAuthorization | null;
  deployment: Deployment | null;
};

export type DeliveryPackage = {
  id: string;
  project_id: string;
  deployment_id: string;
  revision: number;
  status: string;
  filename: string;
  sha256: string;
  size_bytes: number;
  manifest: JsonObject;
  download_url: string;
  created_at: string;
};

export type GithubSync = {
  id: string;
  project_id: string;
  delivery_package_id: string;
  repository_full_name: string;
  branch: string;
  status: string;
  repository_url: string | null;
  error_code: string | null;
};

export type OperationsMetrics = {
  database: JsonObject;
  counts: Record<string, number>;
  recent_failures: Record<string, number>;
  generated_at: string;
};

export type BetaInvite = {
  id: string;
  label: string;
  status: string;
  max_uses: number;
  use_count: number;
  expires_at: string | null;
  created_at: string;
};

export type Backup = {
  id: string;
  mode: string;
  status: string;
  storage_ref: string;
  sha256: string | null;
  size_bytes: number;
  error_code: string | null;
  created_at: string;
  completed_at: string | null;
};

export type AppError = {
  code: string;
  message: string;
  userMessage: string;
  retryable: boolean;
  requestId?: string;
  status?: number;
};


export type ProductionReadiness = {
  service_guides?: Record<string, {title?: string; purpose?: string; console_url?: string; steps?: string[]; cost_note?: string}>;
  storage_mode?: "cloud_database" | "browser_local";
  lightweight_available?: boolean;
  required_environment?: string[];
  missing_environment?: string[];
  code_version: number | null;
  package_ready: boolean;
  preview_accepted: boolean;
  database_connected: boolean;
  database_checked_at: string | null;
  ready: boolean;
};
