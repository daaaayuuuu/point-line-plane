const state = {
  user: null,
  project: null,
  dashboard: null,
  selectedNode: null,
  inspectorTab: "product",
  selectedOptions: {},
  developmentTask: null,
  developmentRun: null,
  developmentWorkspace: null,
  selectedCodeFile: null,
  busy: false,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function readableKey(key) {
  const labels = {
    learning_cost: "学习成本",
    delivery_scope: "开发范围",
    risk: "风险",
    readability: "易读性",
    user_problem: "用户问题",
    expected_result: "预期改善",
    low: "低",
    lowest: "很低",
    medium: "中",
    high: "高",
    small: "小",
    none: "无",
  };
  return labels[key] || key;
}

function compactTechnical(value) {
  if (!value || typeof value !== "object") return String(value ?? "");
  const first = Object.entries(value)[0];
  if (!first) return "技术契约不变";
  const rendered = typeof first[1] === "object" ? JSON.stringify(first[1]) : first[1];
  return `${first[0]}: ${rendered}`;
}

function toast(message, type = "normal") {
  const item = document.createElement("div");
  item.className = `toast ${type === "error" ? "error" : ""}`;
  item.textContent = message;
  $("#toastStack").appendChild(item);
  setTimeout(() => item.remove(), 3600);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: options.body ? { "Content-Type": "application/json", ...(options.headers || {}) } : options.headers,
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const error = payload?.error || {};
    const exception = new Error(error.message || `请求失败（${response.status}）`);
    exception.code = error.code || "HTTP_ERROR";
    exception.traceId = error.trace_id;
    exception.status = response.status;
    throw exception;
  }
  return payload;
}

function showError(error) {
  const suffix = error.traceId ? ` · 追踪号 ${error.traceId.slice(0, 8)}` : "";
  toast(`${error.message || "操作失败"}${suffix}`, "error");
}

async function withBusy(button, label, task) {
  if (state.busy) return;
  state.busy = true;
  const original = button?.innerHTML;
  if (button) {
    button.disabled = true;
    button.textContent = label;
  }
  try {
    await task();
  } catch (error) {
    showError(error);
  } finally {
    state.busy = false;
    if (button) {
      button.disabled = false;
      button.innerHTML = original;
    }
    updateSimulationAction();
  }
}

function setConnection(status, text) {
  const element = $("#connectionState");
  element.className = `connection ${status}`;
  element.innerHTML = `<i></i> ${escapeHtml(text)}`;
}

async function checkConnection() {
  try {
    await api("/api/v1/health");
    setConnection("ready", "第三阶段后端正常");
  } catch {
    setConnection("error", "后端未连接");
  }
}

function setLoggedIn(loggedIn) {
  $("#loginPanel").classList.toggle("hidden", loggedIn);
  $("#experienceContent").classList.toggle("hidden", !loggedIn);
}

async function restoreSession() {
  try {
    const response = await api("/api/v1/auth/me");
    state.user = response.user;
    setLoggedIn(true);
    await loadProjects();
  } catch (error) {
    if (!["AUTH_REQUIRED", "INVALID_SESSION", "SESSION_EXPIRED"].includes(error.code)) {
      showError(error);
    }
    setLoggedIn(false);
  }
}

async function login(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  await withBusy(button, "正在进入…", async () => {
    const displayName = $("#displayNameInput").value.trim();
    const inviteCode = $("#inviteCodeInput").value.trim();
    if (!displayName || !inviteCode) throw new Error("请填写体验名称和测试邀请码。");
    const response = await api("/api/v1/auth/invite-login", {
      method: "POST",
      body: JSON.stringify({ display_name: displayName, invite_code: inviteCode }),
    });
    state.user = response.user;
    setLoggedIn(true);
    toast("已进入第三阶段体验台");
    await loadProjects();
  });
}

async function restartExperience() {
  const button = $("#restartButton");
  await withBusy(button, "正在退出…", async () => {
    try { await api("/api/v1/auth/logout", { method: "POST" }); } catch { /* local reset */ }
    state.user = null;
    state.project = null;
    state.dashboard = null;
    state.selectedNode = null;
    state.selectedOptions = {};
    state.developmentTask = null;
    state.developmentRun = null;
    state.developmentWorkspace = null;
    state.selectedCodeFile = null;
    $("#inviteCodeInput").value = "";
    setLoggedIn(false);
    resetVisuals();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

function resetVisuals() {
  $("#sidebarProjectName").textContent = "体验项目";
  $("#nextActionText").textContent = "登录后生成产品地图";
  $("#projectSetup").classList.add("hidden");
  $("#graphEmpty").classList.remove("hidden");
  $("#journeyGraph").classList.add("hidden");
  $("#nodeInspector").classList.add("hidden");
  $("#decisionList").innerHTML = '<div class="empty-state compact-empty">生成产品地图后，这里会出现需要你判断的产品问题。</div>';
  $("#simulationTimeline").innerHTML = '<div class="empty-timeline">开始走查后，每一步体验和证据会显示在这里。</div>';
  $("#findingPanel").classList.add("hidden");
  $("#changeList").innerHTML = '<div class="empty-state compact-empty">完成决策或处理走查问题后，改动会自动汇总到这里。</div>';
  $("#openDecisionCount").textContent = "0";
  $("#changeCount").textContent = "0";
  $("#initializeGraphButton").disabled = false;
  $("#initializeGraphButton").textContent = "生成产品地图";
  resetDevelopment();
  updateSimulationAction();
}

function resetDevelopment() {
  const status = $("#developmentStatus");
  if (!status) return;
  status.className = "development-status";
  status.innerHTML = '<span class="status-orb">待</span><div><small>当前状态</small><strong>等待开始第三阶段开发</strong><p>点击右上角按钮后，演示页会通过正式 API 补齐示例确认并启动任务。</p></div>';
  $("#toolTimeline").innerHTML = '<div class="empty-timeline">任务开始后，这里会显示每一个受控工具和副作用。</div>';
  $("#codeFileList").innerHTML = '<div class="empty-file-list">生成完成后，可逐个查看文件用途和精确代码。</div>';
  $("#codeViewer").innerHTML = '<div class="code-empty"><span>{ }</span><strong>选择一个文件</strong><small>上方先用产品语言解释，下方保留原始技术代码。</small></div>';
  $("#commitLabel").textContent = "尚未生成";
  $("#fileCountLabel").textContent = "0 个文件";
  $("#developmentActionButton").disabled = !state.project;
  $("#developmentActionButton").innerHTML = '准备并开始开发 <b>→</b>';
}

async function loadProjects() {
  const response = await api("/api/v1/projects");
  if (!response.items.length) {
    state.project = null;
    state.dashboard = null;
    resetVisuals();
    $("#projectSetup").classList.remove("hidden");
    $("#graphEmpty").classList.add("hidden");
    $("#nextActionText").textContent = "先创建一个用于走查的体验项目";
    return;
  }
  state.project = response.items[0];
  $("#sidebarProjectName").textContent = state.project.name;
  await loadDashboard();
}

async function createProject() {
  const button = $("#createProjectButton");
  await withBusy(button, "正在创建…", async () => {
    const name = $("#projectNameInput").value.trim();
    const idea = $("#projectIdeaInput").value.trim();
    if (!name || !idea) throw new Error("请填写项目名称和一句话产品想法。");
    state.project = await api("/api/v1/projects", {
      method: "POST",
      body: JSON.stringify({ name, idea }),
    });
    $("#sidebarProjectName").textContent = state.project.name;
    $("#projectSetup").classList.add("hidden");
    await api(`/api/v1/projects/${state.project.id}/product-graph/initialize`, {
      method: "POST",
    });
    toast("体验项目和产品地图已创建");
    await loadDashboard();
  });
}

async function initializeGraph() {
  if (!state.project) {
    $("#projectSetup").classList.remove("hidden");
    $("#graphEmpty").classList.add("hidden");
    return;
  }
  const button = $("#initializeGraphButton");
  await withBusy(button, "正在生成…", async () => {
    await api(`/api/v1/projects/${state.project.id}/product-graph/initialize`, { method: "POST" });
    toast("产品地图已生成：5 个体验节点、2 个关键决策");
    await loadDashboard();
  });
}

async function loadDashboard() {
  if (!state.project) return;
  try {
    state.dashboard = await api(`/api/v1/projects/${state.project.id}/product-dashboard`);
    renderDashboard();
    await loadDevelopmentState();
  } catch (error) {
    if (error.code === "PRODUCT_GRAPH_NOT_INITIALIZED") {
      state.dashboard = null;
      $("#graphEmpty").classList.remove("hidden");
      $("#journeyGraph").classList.add("hidden");
      $("#initializeGraphButton").disabled = false;
      $("#initializeGraphButton").textContent = "生成产品地图";
      $("#nextActionText").textContent = "生成产品地图，开始可视化走查";
      await loadDevelopmentState();
      return;
    }
    throw error;
  }
}

function renderDashboard() {
  const dashboard = state.dashboard;
  if (!dashboard) return;
  $("#nextActionText").textContent = dashboard.next_action.message;
  $("#graphEmpty").classList.add("hidden");
  $("#journeyGraph").classList.remove("hidden");
  $("#initializeGraphButton").disabled = true;
  $("#initializeGraphButton").textContent = `产品地图 v${dashboard.graph.version} 已生成`;
  renderGraph(dashboard.graph.nodes);
  renderDecisions(dashboard.decision_center);
  renderSimulation(dashboard.latest_simulation, dashboard.open_findings);
  renderChanges(dashboard.queued_changes);
  updateSimulationAction();
}

function nodeTypeLabel(type) {
  return {
    persona: "用户节点",
    input: "输入节点",
    ai_action: "AI 能力节点",
    output: "结果节点",
    persistence: "持续使用节点",
  }[type] || "产品节点";
}

function nodeStatusLabel(status) {
  return {
    ready: "已定义",
    needs_decision: "需要判断",
    issue: "发现问题",
    optimized: "已优化",
  }[status] || status;
}

function renderGraph(nodes) {
  $("#journeyGraph").innerHTML = nodes.map((node, index) => `
    <button class="journey-node ${state.selectedNode?.id === node.id ? "selected" : ""}" type="button" data-node-id="${escapeHtml(node.id)}" role="listitem">
      <span class="node-index">${String(index + 1).padStart(2, "0")}</span>
      <strong>${escapeHtml(node.title)}</strong>
      <small>${escapeHtml(node.caption)}</small>
      <span class="node-state ${escapeHtml(node.status)}">${escapeHtml(nodeStatusLabel(node.status))}</span>
    </button>
  `).join("");
  $$(".journey-node").forEach((button) => button.addEventListener("click", () => openNode(button.dataset.nodeId)));
}

function openNode(nodeId) {
  state.selectedNode = state.dashboard.graph.nodes.find((item) => item.id === nodeId);
  state.inspectorTab = "product";
  renderGraph(state.dashboard.graph.nodes);
  renderInspector();
  $("#nodeInspector").classList.remove("hidden");
  $("#nodeInspector").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function contractRows(contract) {
  return Object.entries(contract || {}).map(([key, value]) => `
    <div class="contract-row">
      <span>${escapeHtml(key)}</span>
      <code>${escapeHtml(typeof value === "object" ? JSON.stringify(value, null, 2) : value)}</code>
    </div>
  `).join("");
}

function renderInspector() {
  const node = state.selectedNode;
  if (!node) return;
  const index = state.dashboard.graph.nodes.findIndex((item) => item.id === node.id) + 1;
  $("#inspectorBadge").textContent = String(index).padStart(2, "0");
  $("#inspectorType").textContent = nodeTypeLabel(node.node_type);
  $("#inspectorTitle").textContent = node.title;
  $$("[data-inspector-tab]").forEach((button) => button.classList.toggle("active", button.dataset.inspectorTab === state.inspectorTab));
  const body = $("#inspectorBody");
  if (state.inspectorTab === "product") {
    body.innerHTML = `<h4>这一节点为什么存在</h4><p>${escapeHtml(node.product_purpose)}</p><h4 style="margin-top:18px">用户会看到</h4><p>${escapeHtml(node.user_sees)}</p>`;
  } else if (state.inspectorTab === "system") {
    body.innerHTML = `<h4>系统在背后完成</h4><p>${escapeHtml(node.system_does)}</p><p style="margin-top:14px;color:#66738d">这里使用产品语言解释过程，但不会改写接口名、数据字段或技术边界。</p>`;
  } else {
    body.innerHTML = `<h4>精确技术契约</h4><div class="contract-grid">${contractRows(node.technical_contract)}</div>`;
  }
}

function renderDecisions(center) {
  $("#openDecisionCount").textContent = center.open_count;
  if (!center.items.length) {
    $("#decisionList").innerHTML = '<div class="empty-state compact-empty">当前没有需要确认的决策。</div>';
    return;
  }
  $("#decisionList").innerHTML = center.items.map((decision) => {
    const selected = state.selectedOptions[decision.id] || decision.selected_option_key;
    return `
      <article class="decision-card ${decision.status === "confirmed" ? "confirmed" : ""}">
        <header class="decision-header">
          <div><h3>${escapeHtml(decision.title)}</h3><p>${escapeHtml(decision.question)}</p></div>
          <span class="decision-status">${decision.status === "confirmed" ? "✓ 已确认" : "等待你的判断"}</span>
        </header>
        <div class="option-grid">
          ${decision.options.map((option) => `
            <button class="option-card ${selected === option.key ? "selected" : ""}" type="button" data-decision-id="${escapeHtml(decision.id)}" data-option-key="${escapeHtml(option.key)}" ${decision.status === "confirmed" ? "disabled" : ""}>
              ${option.recommended ? '<span class="recommended">推荐</span>' : ""}
              <strong>${escapeHtml(option.title)}</strong>
              <p>${escapeHtml(option.description)}</p>
              <div class="impact-row">${Object.entries(option.product_impact).map(([key, value]) => `<span class="impact-chip">${escapeHtml(readableKey(key))}：${escapeHtml(readableKey(value))}</span>`).join("")}</div>
              <div class="tech-effect">${escapeHtml(compactTechnical(option.technical_effects))}</div>
            </button>
          `).join("")}
        </div>
        ${decision.status === "open" ? `<footer class="decision-footer"><button class="primary-button small confirm-decision" type="button" data-decision-id="${escapeHtml(decision.id)}" ${selected ? "" : "disabled"}>确认这个产品选择 <b>→</b></button></footer>` : ""}
      </article>
    `;
  }).join("");
  $$(".option-card").forEach((button) => button.addEventListener("click", () => selectDecisionOption(button.dataset.decisionId, button.dataset.optionKey)));
  $$(".confirm-decision").forEach((button) => button.addEventListener("click", () => confirmDecision(button.dataset.decisionId, button)));
}

function selectDecisionOption(decisionId, optionKey) {
  state.selectedOptions[decisionId] = optionKey;
  renderDecisions(state.dashboard.decision_center);
}

async function confirmDecision(decisionId, button) {
  const optionKey = state.selectedOptions[decisionId];
  if (!optionKey) return;
  await withBusy(button, "正在确认…", async () => {
    await api(`/api/v1/decisions/${decisionId}/confirm`, {
      method: "POST",
      body: JSON.stringify({ option_key: optionKey, idempotency_key: `ui-decision-${decisionId}` }),
    });
    toast("产品决策已保存，并形成一条可追溯改动");
    await loadDashboard();
  });
}

function renderSimulation(run, openFindings) {
  if (!run) {
    $("#simulationTimeline").innerHTML = '<div class="empty-timeline">开始走查后，每一步体验和证据会显示在这里。</div>';
    $("#findingPanel").classList.add("hidden");
    return;
  }
  const statusIcon = (status) => status === "passed" ? "✓" : "!";
  $("#simulationTimeline").innerHTML = run.steps.length ? run.steps.map((step) => `
    <div class="timeline-step ${escapeHtml(step.status)}">
      <span class="timeline-dot">${statusIcon(step.status)}</span>
      <div>
        <strong>${escapeHtml(step.node_title)}</strong>
        <small>${escapeHtml(step.observation)}</small>
        <button class="evidence-toggle" type="button">查看技术证据</button>
        <pre class="evidence-block hidden">${escapeHtml(JSON.stringify(step.technical_evidence, null, 2))}</pre>
      </div>
      <time>${step.duration_ms}ms</time>
    </div>
  `).join("") : '<div class="empty-timeline">虚拟用户已就位，点击“继续下一步”。</div>';
  $$(".evidence-toggle").forEach((button) => button.addEventListener("click", () => {
    const block = button.nextElementSibling;
    block.classList.toggle("hidden");
    button.textContent = block.classList.contains("hidden") ? "查看技术证据" : "收起技术证据";
  }));

  const finding = openFindings?.[0];
  if (!finding) {
    $("#findingPanel").classList.add("hidden");
    return;
  }
  $("#findingPanel").classList.remove("hidden");
  $("#findingPanel").innerHTML = `
    <div class="finding-heading">
      <span class="finding-icon">!</span>
      <div><h3>虚拟用户在“输入”这一步停下了</h3><p>${escapeHtml(finding.product_summary)}</p></div>
    </div>
    <div class="resolution-grid">
      ${finding.resolution_options.map((option) => `
        <button class="resolution-option" type="button" data-finding-id="${escapeHtml(finding.id)}" data-resolution-key="${escapeHtml(option.key)}">
          <strong>${escapeHtml(option.title)}</strong>
          <small>${escapeHtml(option.description)}</small>
          ${option.recommended ? '<span class="recommended">推荐处理</span>' : ""}
        </button>
      `).join("")}
    </div>
  `;
  $$(".resolution-option").forEach((button) => button.addEventListener("click", () => resolveFinding(button.dataset.findingId, button.dataset.resolutionKey, button)));
}

function updateSimulationAction() {
  const button = $("#simulationActionButton");
  const run = state.dashboard?.latest_simulation;
  if (!state.dashboard) {
    button.disabled = true;
    button.innerHTML = "先生成产品地图";
    return;
  }
  if (!run) {
    button.disabled = false;
    button.innerHTML = "开始用户走查 <b>→</b>";
  } else if (run.status === "blocked") {
    button.disabled = true;
    button.innerHTML = "请先处理发现的问题";
  } else if (run.status === "succeeded") {
    button.disabled = false;
    button.innerHTML = "重新走查 <b>→</b>";
  } else {
    button.disabled = false;
    button.innerHTML = "让用户继续下一步 <b>→</b>";
  }
}

async function simulationAction() {
  const button = $("#simulationActionButton");
  const run = state.dashboard?.latest_simulation;
  await withBusy(button, "正在走查…", async () => {
    if (!run || run.status === "succeeded") {
      await api(`/api/v1/product-graphs/${state.dashboard.graph.id}/simulations`, {
        method: "POST",
        body: JSON.stringify({
          persona_key: "first_time_non_technical_user",
          idempotency_key: `ui-simulation-${Date.now()}`,
        }),
      });
      toast("虚拟用户已经进入产品");
    } else {
      await api(`/api/v1/simulations/${run.id}/advance`, { method: "POST" });
    }
    await loadDashboard();
    $("#simulationTimeline").scrollIntoView({ behavior: "smooth", block: "center" });
  });
}

async function resolveFinding(findingId, resolutionKey, button) {
  await withBusy(button, "正在保存处理…", async () => {
    await api(`/api/v1/findings/${findingId}/resolve`, {
      method: "POST",
      body: JSON.stringify({
        resolution_key: resolutionKey,
        idempotency_key: `ui-finding-${findingId}-${resolutionKey}`,
      }),
    });
    toast("问题已处理，并形成一条改动请求");
    await loadDashboard();
  });
}

function renderChanges(changes) {
  $("#changeCount").textContent = changes.length;
  if (!changes.length) {
    $("#changeList").innerHTML = '<div class="empty-state compact-empty">完成决策或处理走查问题后，改动会自动汇总到这里。</div>';
    return;
  }
  $("#changeList").innerHTML = changes.map((change) => `
    <article class="change-card">
      <span class="change-source">${change.source_type === "decision" ? "决" : "查"}</span>
      <div>
        <h3>${escapeHtml(change.product_request)}</h3>
        <p>来源：${change.source_type === "decision" ? "你的产品决策" : "虚拟用户走查"} · 范围：已确认范围内 · 状态：已确认</p>
      </div>
      <div class="change-tech">${escapeHtml(compactTechnical(change.technical_context))}</div>
    </article>
  `).join("");
}

const toolLabels = {
  context_loader: ["读取确认内容", "只读取 PRD、方案、决策和改动，不修改文件"],
  coding_provider: ["生成代码包", "仅调用已配置模型边界，输出必须通过结构校验"],
  workspace_writer: ["写入隔离工作区", "只允许当前项目和白名单文件路径"],
  git_checkpoint: ["保存 Git 版本", "创建可追溯的 40 位 commit，不执行部署"],
};

function renderDevelopment(run, workspace) {
  state.developmentRun = run;
  state.developmentWorkspace = workspace;
  if (!run) {
    resetDevelopment();
    return;
  }
  const labels = {
    queued: ["排", "开发任务已排队", "后台会自动继续，可以关闭页面。"],
    running: ["做", "正在生成代码", `当前步骤：${run.current_step}`],
    succeeded: ["✓", "代码版本已经保存", "你可以逐个查看文件用途和原始代码。"],
    failed: ["!", "开发已暂停", `错误类型：${run.error_code || "待排查"}`],
  };
  const [icon, title, description] = labels[run.status] || labels.running;
  const status = $("#developmentStatus");
  status.className = `development-status ${escapeHtml(run.status)}`;
  status.innerHTML = `<span class="status-orb">${escapeHtml(icon)}</span><div><small>当前状态</small><strong>${escapeHtml(title)}</strong><p>${escapeHtml(description)}</p></div>`;

  const completedTools = new Set(run.tools.filter((item) => item.status === "succeeded").map((item) => item.tool_name));
  $("#developmentPlan").innerHTML = (run.plan?.steps || []).map((step, index) => `
    <div class="${completedTools.has(step.technical_action) ? "completed" : ""}"><span>${completedTools.has(step.technical_action) ? "✓" : index + 1}</span><strong>${escapeHtml(step.product_language)}</strong></div>
  `).join("");

  $("#toolTimeline").innerHTML = run.tools.length ? run.tools.map((tool) => {
    const [name, explanation] = toolLabels[tool.tool_name] || [tool.tool_name, "受控后台动作"];
    const symbol = tool.status === "succeeded" ? "✓" : tool.status === "failed" ? "!" : "…";
    return `<div class="tool-item ${escapeHtml(tool.status)}"><span class="tool-icon">${symbol}</span><div><strong>${escapeHtml(name)}</strong><small>${escapeHtml(explanation)}</small></div><span class="tool-side-effect">${escapeHtml(tool.side_effect)}</span></div>`;
  }).join("") : '<div class="empty-timeline">正在等待第一个后台动作。</div>';

  const files = run.files || [];
  $("#fileCountLabel").textContent = `${files.length} 个文件`;
  $("#commitLabel").textContent = workspace?.current_commit_ref ? `Git ${workspace.current_commit_ref.slice(0, 10)}` : "正在保存版本";
  $("#codeFileList").innerHTML = files.length ? files.map((file) => `
    <button class="file-button ${state.selectedCodeFile?.id === file.id ? "active" : ""}" type="button" data-file-id="${escapeHtml(file.id)}">${escapeHtml(file.path)}</button>
  `).join("") : '<div class="empty-file-list">代码文件还在生成，请稍候。</div>';
  $$(".file-button").forEach((button) => button.addEventListener("click", () => openCodeFile(button.dataset.fileId)));

  const action = $("#developmentActionButton");
  if (run.status === "succeeded") action.innerHTML = '查看已生成代码 <b>↓</b>';
  else if (run.status === "failed") action.innerHTML = "查看失败状态";
  else action.innerHTML = "后台开发中…";
}

async function openCodeFile(fileId) {
  const metadata = state.developmentRun?.files.find((item) => item.id === fileId);
  if (!metadata || !state.developmentRun?.code_version_id) return;
  const safePath = metadata.path.split("/").map(encodeURIComponent).join("/");
  try {
    const file = await api(`/api/v1/code-versions/${state.developmentRun.code_version_id}/files/${safePath}`);
    state.selectedCodeFile = file;
    renderDevelopment(state.developmentRun, state.developmentWorkspace);
    $("#codeViewer").innerHTML = `<div class="file-purpose"><strong>${escapeHtml(file.path)}</strong><small>${escapeHtml(file.product_purpose)}</small></div><pre>${escapeHtml(file.content)}</pre>`;
  } catch (error) {
    showError(error);
  }
}

async function loadDevelopmentState() {
  if (!state.project) {
    resetDevelopment();
    return;
  }
  try {
    const response = await api(`/api/v1/projects/${state.project.id}/development-runs`);
    if (!response.items.length) {
      resetDevelopment();
      return;
    }
    const run = response.items[0];
    const workspace = await api(`/api/v1/projects/${state.project.id}/development-workspace`);
    renderDevelopment(run, workspace);
    if (["queued", "running"].includes(run.status)) pollDevelopmentTask(run.task_id, 50).catch(showError);
  } catch (error) {
    if (error.code === "DEVELOPMENT_WORKSPACE_NOT_READY") resetDevelopment();
    else throw error;
  }
}

async function prepareProjectForDevelopment() {
  let detail = await api(`/api/v1/projects/${state.project.id}`);
  const answers = {
    target_user: "面向第一次使用的非技术产品经理，帮助他把一段文字整理成结构化结果。",
    core_output: "输出一段摘要、三条关键要点和一个明确下一步。",
    success_criteria: "提交非空文本后能得到结构化结果，刷新后仍能看到历史记录。",
  };
  for (let step = 0; step < 12; step += 1) {
    if (["DEVELOPMENT", "PREVIEW_REVIEW"].includes(detail.stage)) return detail;
    if (detail.stage === "PAUSED") throw new Error("当前项目已暂停，请先查看失败说明。");
    if (detail.stage === "REQUIREMENTS") {
      const question = detail.next_action?.questions?.[0];
      if (!question) throw new Error("没有找到当前需求问题。");
      const result = await api(`/api/v1/projects/${state.project.id}/requirements/messages`, {
        method: "POST",
        body: JSON.stringify({ question_id: question.id, message: answers[question.id] || "按首版推荐范围处理。" }),
      });
      detail = result.project;
      continue;
    }
    if (detail.stage === "PRD_REVIEW") {
      const artifacts = await api(`/api/v1/projects/${state.project.id}/artifacts?type=prd`);
      const current = artifacts.items.find((item) => item.status === "draft") || artifacts.items[0];
      const result = await api(`/api/v1/projects/${state.project.id}/confirmations/prd`, {
        method: "POST",
        body: JSON.stringify({ artifact_id: current.id, decision: "confirm" }),
      });
      detail = result.project;
      continue;
    }
    if (detail.stage === "SOLUTION_REVIEW") {
      const artifacts = await api(`/api/v1/projects/${state.project.id}/artifacts?type=solution`);
      const current = artifacts.items.find((item) => item.status === "draft") || artifacts.items[0];
      const result = await api(`/api/v1/projects/${state.project.id}/confirmations/solution`, {
        method: "POST",
        body: JSON.stringify({ artifact_id: current.id, decision: "confirm" }),
      });
      detail = result.project;
      continue;
    }
  }
  throw new Error("示例确认流程没有在限制步骤内完成。");
}

async function pollDevelopmentTask(taskId, maxRounds = 100) {
  for (let round = 0; round < maxRounds; round += 1) {
    const task = await api(`/api/v1/tasks/${taskId}`);
    state.developmentTask = task;
    const runId = task.checkpoint?.development_run_id;
    if (runId) {
      const run = await api(`/api/v1/development-runs/${runId}`);
      const workspace = await api(`/api/v1/projects/${state.project.id}/development-workspace`);
      renderDevelopment(run, workspace);
    }
    if (["succeeded", "failed"].includes(task.status)) return task;
    await new Promise((resolve) => setTimeout(resolve, 180));
  }
  throw new Error("后台任务仍在运行，可稍后刷新页面继续查看。");
}

async function startDevelopmentExperience() {
  const button = $("#developmentActionButton");
  if (state.developmentRun?.status === "succeeded") {
    $("#codeFileList").scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  await withBusy(button, "正在准备确认内容…", async () => {
    if (!state.project) throw new Error("请先创建体验项目。");
    const detail = await prepareProjectForDevelopment();
    if (detail.stage === "PREVIEW_REVIEW") {
      await loadDevelopmentState();
      return;
    }
    const task = await api(`/api/v1/projects/${state.project.id}/development/start`, { method: "POST" });
    state.developmentTask = task;
    toast("第三阶段开发已受理，页面会显示每个后台动作");
    await pollDevelopmentTask(task.id);
    await loadDevelopmentState();
    toast("真实代码文件和 Git 版本已经保存");
  });
}

function bindEvents() {
  $("#loginForm").addEventListener("submit", login);
  $("#restartButton").addEventListener("click", restartExperience);
  $("#createProjectButton").addEventListener("click", createProject);
  $("#initializeGraphButton").addEventListener("click", initializeGraph);
  $("#simulationActionButton").addEventListener("click", simulationAction);
  $("#developmentActionButton").addEventListener("click", startDevelopmentExperience);
  $("#closeInspectorButton").addEventListener("click", () => $("#nodeInspector").classList.add("hidden"));
  $$("[data-inspector-tab]").forEach((button) => button.addEventListener("click", () => {
    state.inspectorTab = button.dataset.inspectorTab;
    renderInspector();
  }));
  $$(".stage-item").forEach((button) => button.addEventListener("click", () => {
    $$(".stage-item").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    document.getElementById(button.dataset.target)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }));
}

async function boot() {
  bindEvents();
  resetVisuals();
  await checkConnection();
  await restoreSession();
}

boot();
