import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server renders the product factory shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<title>点线面｜从产品想法到正式交付<\/title>/i);
  assert.match(html, /正在恢复你的产品进度/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Starter Project/);
  assert.match(html, /lang="zh-CN"/);
});

test("shows four user phases while keeping the internal production architecture", async () => {
  const [app, stepper, stepCheck, stepCompleteTail, stepPendingTail, historyEmpty, stages, panels, requirements, visualSolution, development, uiStyles, preview, operations, usage, deployment, delivery, css, tokens, packageJson] = await Promise.all([
    readFile(new URL("../features/factory/ProductFactoryApp.tsx", import.meta.url), "utf8"),
    readFile(new URL("../features/factory/BossSteps.tsx", import.meta.url), "utf8"),
    readFile(new URL("../public/boss-step-check-outlined.svg", import.meta.url), "utf8"),
    readFile(new URL("../public/boss-step-tail-complete.svg", import.meta.url), "utf8"),
    readFile(new URL("../public/boss-step-tail-pending.svg", import.meta.url), "utf8"),
    readFile(new URL("../public/history-record-empty.png", import.meta.url)),
    readFile(new URL("../features/factory/data.ts", import.meta.url), "utf8"),
    readFile(new URL("../features/factory/StagePanels.tsx", import.meta.url), "utf8"),
    readFile(new URL("../features/factory/stages/M1ARequirements.tsx", import.meta.url), "utf8"),
    readFile(new URL("../features/factory/stages/SolutionVisualDecisionView.tsx", import.meta.url), "utf8"),
    readFile(new URL("../features/factory/stages/M1CDevelopment.tsx", import.meta.url), "utf8"),
    readFile(new URL("../features/factory/UiStylePicker.tsx", import.meta.url), "utf8"),
    readFile(new URL("../features/factory/stages/M1DPreview.tsx", import.meta.url), "utf8"),
    readFile(new URL("../features/factory/stages/M3M4Operations.tsx", import.meta.url), "utf8"),
    readFile(new URL("../features/factory/stages/M2AUsage.tsx", import.meta.url), "utf8"),
    readFile(new URL("../features/factory/stages/M2BDeployment.tsx", import.meta.url), "utf8"),
    readFile(new URL("../features/factory/stages/M2CDelivery.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../app/design-tokens.css", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);
  for (const code of ["M1A", "M1B", "M1C", "M1D", "M2A", "M2B", "M2C", "M3/M4"]) {
    assert.match(stages, new RegExp(code.replace("/", "\\/")));
  }
  for (const phase of ["上传点子或 PRD", "确认方案", "生成与预览", "部署与上线"]) {
    assert.match(stages, new RegExp(phase));
  }
  assert.match(stages, /PRODUCT_PHASES/);
  assert.match(stages, /getCurrentPhaseIndex/);
  assert.match(stages, /getDefaultStageForPhase/);
  assert.match(panels, /visual-solution/);
  assert.doesNotMatch(panels, /label: "产品方案"/);
  assert.doesNotMatch(panels, /label: "产品流程"/);
  assert.match(visualSolution, /可点击界面故事板/);
  assert.match(visualSolution, /低保真方案/);
  assert.match(visualSolution, /生成真实 HTML/);
  assert.match(visualSolution, /UiStylePicker/);
  assert.doesNotMatch(panels, /label: "生成进度"/);
  assert.doesNotMatch(panels, /label: "产品预览"/);
  assert.match(panels, /m1c: <M1DPreview/);
  assert.match(panels, /发布产品/);
  assert.match(panels, /交付内容/);
  assert.doesNotMatch(panels, /label: "稳定运营"/);
  assert.doesNotMatch(app, /服务连接中|进度已自动保存/);
  assert.match(app, /factory-sidebar/);
  assert.doesNotMatch(app, /workspace-stage-banner/);
  assert.match(app, /sidebar-account/);
  assert.match(app, /accountInitial/);
  assert.match(app, /className="user-avatar"/);
  assert.match(app, /title=\{accountName\}/);
  assert.match(app, /<span><strong>点线面<\/strong><small>AI 产品交付平台<\/small><\/span>/);
  assert.doesNotMatch(app, /<span><strong>\{project\.name\}<\/strong>/);
  assert.match(app, /item\.idea \|\| "暂无项目描述"/);
  assert.doesNotMatch(app, /PRODUCT_PHASES\[itemPhaseIndex\]/);
  assert.doesNotMatch(app, /sidebar-projects-link/);
  assert.match(app, /sidebar-project-list/);
  assert.match(app, /暂无项目/);
  assert.match(app, /请先前往创建项目/);
  assert.doesNotMatch(app, /暂未创建任何项目/);
  assert.match(app, /sidebar-project-empty-art/);
  assert.match(app, /items\[0\]\.id/);
  assert.doesNotMatch(app, /workspace-toolbar-actions/);
  assert.doesNotMatch(app, /我的项目/);
  assert.match(app, /sidebar-create-project/);
  assert.match(app, /inline-create-project/);
  assert.match(app, /创建你的新项目/);
  assert.match(app, /填写项目名称和项目描述/);
  assert.match(app, /<label>项目名称<input/);
  assert.match(app, /<label>项目描述<textarea/);
  assert.match(app, /例如：桌面番茄闹钟/);
  assert.match(app, /帮助用户进行工作计时、保持专注并完成任务/);
  assert.doesNotMatch(app, /客服知识库助手|整理分散的客服问答/);
  assert.doesNotMatch(app, /你想创造什么产品|<label>产品名称<input|<label>一句产品想法<textarea/);
  assert.match(app, /api\.createProject/);
  assert.doesNotMatch(app, /\$\{projects\.length\} 个产品 · 创建与管理/);
  assert.doesNotMatch(app, /create-guide-card/);
  assert.match(app, /sidebar-project-delete/);
  assert.match(app, /DeleteProjectDialog/);
  assert.match(app, /确认删除/);
  assert.match(app, /api\.deleteProject/);
  assert.doesNotMatch(app, /继续创造你的|继续项目/);
  assert.doesNotMatch(app, /从一句产品想法开始/);
  assert.match(app, /你的第一个项目/);
  assert.doesNotMatch(app, /先创建一个项目，/);
  assert.match(app, /输入产品想法或上传 PRD/);
  assert.match(app, /平台会协助梳理需求/);
  assert.doesNotMatch(app, /Codex 会协助梳理需求/);
  assert.doesNotMatch(app, /完成部署上线。/);
  assert.match(app, /梳理需求、确认方案、生成预览并完成部署上线/);
  assert.doesNotMatch(app, /new-project-card/);
  assert.match(app, /projects\.length === 0/);
  assert.match(app, /AI 产品交付平台/);
  assert.doesNotMatch(app, /AI 产品工厂/);
  assert.doesNotMatch(app, /本地体验环境|本地开发环境|预填|体验用户|体验邀请码|当前演示版|local-development/);
  assert.doesNotMatch(operations, /本地开发|预填|local-development/);
  assert.doesNotMatch(usage, /体验计划|本地模拟模型/);
  assert.doesNotMatch(app, /modal-backdrop/);
  assert.doesNotMatch(app, /个人中心/);
  assert.match(app, /退出登录/);
  assert.match(panels, /step: phaseIndex \+ 1/);
  assert.doesNotMatch(app, /第 \{currentPhaseIndex \+ 1\} \/ 4 步/);
  assert.match(stepper, /产品创建进度/);
  assert.match(stepper, /const completed = !current && index < completedBeforeIndex/);
  assert.doesNotMatch(app, /sidebar-stages|产品生产流程|后续步骤/);
  assert.doesNotMatch(app, /产品开发八阶段|共 8 步|八阶段交付流程/);
  assert.match(requirements, /先体验低保真方案，再生成高保真 UI/);
  assert.match(requirements, /方案没问题，生成高保真 UI/);
  assert.match(stages, /用低保真界面故事板走一遍关键操作/);
  assert.doesNotMatch(stages, /看懂产品范围、使用流程、实现方式、费用与风险/);
  assert.doesNotMatch(requirements, /个产物版本/);
  assert.match(requirements, /上传文档、代码或压缩包/);
  assert.match(requirements, /发送给 Codex/);
  assert.match(requirements, /api\.uploadRequirement/);
  assert.match(requirements, /prd-copilot-workbench/);
  assert.match(requirements, /Codex 产品助手/);
  assert.match(requirements, /<h1><span>我是您的 AI 产品助手<\/span><span>我能帮您创建什么？<\/span><\/h1>/);
  assert.match(requirements, /label: "梳理产品目标和核心问题"/);
  assert.match(requirements, /label: "定义目标用户和使用场景"/);
  assert.match(requirements, /label: "设计首版功能和操作流程"/);
  assert.match(requirements, /label: "审查并完善产品需求"/);
  assert.match(requirements, /label: "生成可确认的产品需求文档"/);
  assert.match(requirements, /<ul className="codex-guide-list"/);
  assert.doesNotMatch(requirements, /chooseStarter/);
  assert.match(requirements, /codex-command-composer/);
  assert.match(requirements, /className="codex-message-content"/);
  assert.doesNotMatch(requirements, /item\.role === "assistant" && <span><CodexMark/);
  assert.doesNotMatch(requirements, /item\.role === "assistant" \? "Codex" : "你"/);
  assert.match(requirements, /输入产品点子，或上传尚未完善的 PRD，我来帮你生成完整的 PRD 文档/);
  assert.match(requirements, /5\.6 Sol/);
  assert.match(requirements, /极高/);
  assert.match(requirements, /aria-label="添加文件"/);
  assert.match(requirements, /fileInputRef\.current\?\.click\(\)/);
  for (const extension of [".md", ".pdf", ".sql", ".docx", ".xlsx", ".pptx", ".zip", ".tar.gz"]) {
    assert.match(requirements, new RegExp(extension.replace(".", "\\.")));
  }
  assert.doesNotMatch(requirements, /codex-attachment-menu|粘贴产品想法|openComposerMenu === "attachments"/);
  assert.match(requirements, /codex-model-menu/);
  assert.match(requirements, /开始听写/);
  assert.match(requirements, /codex-stop-button/);
  assert.match(requirements, /停止生成/);
  assert.match(requirements, /generationAbortRef/);
  assert.match(requirements, /controller\.signal/);
  assert.ok(requirements.indexOf('setAnswer("");') < requirements.indexOf("await api.sendCodexMessage"));
  assert.match(requirements, /codex-mic-button/);
  assert.match(requirements, /webkitSpeechRecognition/);
  assert.doesNotMatch(requirements, /codex-access-mode|完全访问/);
  assert.match(requirements, /产品需求文档/);
  assert.match(requirements, /随对话实时更新/);
  assert.match(requirements, /prd-confirmation-bar/);
  assert.match(requirements, /确认后自动生成推荐方案，并进入第 2 步/);
  assert.match(requirements, /aria-label="产品需求确认操作"/);
  assert.match(requirements, /draft \?\? currentArtifact\?\.content/);
  assert.match(requirements, /showGenericPrdPreview = !outputStream && !storedPreviewContent/);
  assert.match(requirements, /previewResetForConversation/);
  assert.match(requirements, /PRD_THINKING_STEPS/);
  assert.match(requirements, /function localizeReasoningLine/);
  assert.match(requirements, /Clarifying\\s\+/);
  assert.match(requirements, /正在确认\$\{subject\}的含义和使用场景/);
  assert.match(requirements, /function CodexChoiceQuestion/);
  assert.match(requirements, /question\.mode === "multiple"/);
  assert.match(requirements, /role=\{multiple \? "checkbox" : "radio"\}/);
  assert.match(requirements, /codex-choice-supplement/);
  assert.match(requirements, /请输入你的具体需求/);
  assert.match(requirements, /其他：\$\{choiceSupplement\.trim\(\)\}/);
  assert.match(requirements, /确认选择/);
  assert.match(requirements, /读取你的产品想法/);
  assert.match(requirements, /把内容逐字写入右侧 PRD/);
  assert.match(requirements, /revealPrdContent/);
  assert.match(requirements, /正在逐字生成/);
  assert.doesNotMatch(requirements, /Codex 正在整理/);
  assert.match(requirements, /番茄时间闹钟/);
  for (const tag of ["25 分钟专注", "5 分钟休息", "网页工具", "到时提醒"]) {
    assert.match(requirements, new RegExp(tag));
  }
  assert.match(requirements, /prd-preview-pane\$\{showGenericPrdPreview \? " is-placeholder" : ""\}/);
  assert.match(requirements, /通用产品需求文档预览/);
  assert.match(requirements, /开始对话后由真实需求替换/);
  assert.match(requirements, /PrdStructuredContent/);
  for (const section of ["目标用户", "核心问题", "产品方案", "核心使用流程", "主要功能", "首版范围", "完成标准", "补充说明"]) {
    assert.match(requirements, new RegExp(section));
  }
  assert.match(requirements, /function DoubleRingTargetIcon\(\)/);
  assert.match(requirements, /data-rings="2"/);
  assert.equal((requirements.match(/<circle cx="9" cy="9"/g) ?? []).length, 2);
  assert.match(requirements, /PrdSectionHeading icon="computer" title="产品方案"/);
  assert.match(requirements, /PrdSectionHeading icon="checkbox" title="完成标准"/);
  assert.match(requirements, /PrdSectionHeading icon="live-notice" title="补充说明"/);
  assert.match(requirements, /<strong>标准 \{index \+ 1\}<\/strong><p>\{item\}<\/p>/);
  assert.doesNotMatch(requirements, /<Check size=\{13\} \/>/);
  assert.doesNotMatch(requirements, /PRODUCT REQUIREMENTS DOCUMENT|prd-placeholder-pill/);
  assert.doesNotMatch(requirements, /Agent 产品交付蓝图|从一个产品想法，到真正能运行的 Agent 产品/);
  assert.match(requirements, /response\.reply/);
  assert.match(requirements, /function withoutTerminalPeriods\(value: string\): string/);
  assert.match(requirements, /replace\(\/\[。.\]\+\$\/g, ""\)/);
  assert.match(requirements, /<p>\{withoutTerminalPeriods\(String\(previewContent\?\.summary \?\? ""\)\)\}/);
  assert.match(requirements, /const PRD_THINKING_STEP_SECONDS = \[0, 2, 6, 12, 20, 32, 48, 68, 90\]/);
  assert.match(requirements, /Codex 正在深度思考/);
  assert.doesNotMatch(requirements, /等待 Codex 返回完整内容/);
  assert.match(css, /\.prd-copilot-workbench/);
  assert.match(css, /\.prd-preview-pane\.is-placeholder \{[^}]*--prd-placeholder-heading-color: var\(--boss-text-base\);[^}]*--prd-placeholder-icon-color: var\(--boss-icon-dark\);[^}]*--prd-placeholder-body-color: color-mix\(in srgb, var\(--boss-text-base\) 92%, var\(--boss-text-secondary\)\);[^}]*opacity: \.5;/s);
  assert.match(css, /\.codex-welcome h1 \{[^}]*font-size: 24px;/);
  assert.match(css, /\.prd-assistant-intro h1 \{[^}]*font-size: 24px;/);
  assert.match(css, /\.prd-document-heading h2 \{[^}]*font-size: 32px;/);
  assert.match(css, /\.prd-preview-header small \{[^}]*font-size: var\(--text-body-sm\);[^}]*line-height: var\(--leading-body-sm\);/);
  assert.match(css, /\.prd-preview-header\.is-placeholder > span:first-child \{ color: var\(--prd-placeholder-icon-color\); \}/);
  assert.match(css, /\.prd-preview-header\.is-placeholder strong \{ color: var\(--prd-placeholder-heading-color\); \}/);
  assert.match(css, /\.prd-preview-header\.is-placeholder small \{ color: var\(--prd-placeholder-body-color\); \}/);
  assert.match(css, /\.prd-preview-header\.is-placeholder > span:first-child:not\(\.prd-codex-mark\) \{ background: var\(--boss-bg-surface-hover\); \}/);
  assert.match(css, /\.prd-placeholder-document \.prd-document-heading h2 \{ color: var\(--prd-placeholder-heading-color\); \}/);
  assert.match(css, /\.prd-placeholder-document \.prd-document-heading > p \{ color: var\(--prd-placeholder-body-color\); \}/);
  assert.match(css, /\.prd-placeholder-document \.prd-template-tags span \{[^}]*color: var\(--boss-text-primary\);[^}]*background: var\(--boss-bg-primary-light\);[^}]*border: 0;/s);
  assert.match(css, /\.prd-structured-content\.is-placeholder \{ --prd-body-color: var\(--prd-placeholder-body-color\); \}/);
  assert.match(css, /\.prd-document-heading > p \{[^}]*color: var\(--boss-text-secondary\);/);
  assert.match(css, /\.prd-definition-rail \{[^}]*border-left: 2px solid var\(--boss-border-primary\);/);
  assert.match(css, /\.prd-insight-card header strong \{[^}]*font-size: var\(--text-body\);[^}]*font-weight: 600;/);
  assert.match(css, /\.prd-section-heading h3 \{[^}]*font-size: var\(--text-body\);[^}]*line-height: var\(--leading-body\);[^}]*font-weight: 600;/);
  for (const icon of ["computer", "checkbox", "live-notice"]) {
    assert.match(css, new RegExp(`\\.prd-section-heading-icon\\.is-${icon} \\{[^}]*mask-image: url\\("/hd-icon-${icon}\\.svg"\\);`));
  }
  for (const selector of ["scope-grid", "notes-grid"]) {
    assert.match(css, new RegExp(`\\.prd-${selector} strong \\{[^}]*font-size: var\\(--text-body-sm\\);[^}]*line-height: var\\(--leading-body-sm\\);`));
  }
  assert.doesNotMatch(css, /\.prd-feature-list > li::before/);
  assert.match(css, /\.prd-plan-step > header > span \{[^}]*background: var\(--boss-bg-primary-light-hover\);/);
  assert.match(css, /\.prd-scope-grid ul \{[^}]*padding-left: 0;[^}]*list-style: none;/);
  assert.match(css, /\.prd-scope-grid > div \+ div \{[^}]*padding-left: 0;[^}]*border-left: 0;[^}]*text-align: left;/);
  assert.match(css, /\.prd-acceptance-list li \{[^}]*grid-template-columns: 96px minmax\(0, 1fr\);[^}]*border-bottom: 1px solid var\(--boss-border-light\);/);
  assert.match(css, /\.prd-acceptance-list strong \{[^}]*font-size: var\(--text-body-sm\);/);
  assert.match(css, /\.prd-acceptance-list \{[^}]*padding: 0 0 0 29px;/);
  assert.match(css, /\.prd-notes-grid \{[^}]*padding-left: 29px;/);
  assert.match(css, /\.prd-notes-grid ul \{[^}]*padding-left: 0;[^}]*list-style: none;/);
  assert.match(css, /\.prd-assistant-pane/);
  assert.match(css, /\.prd-preview-pane/);
  assert.match(css, /\.codex-guide-list/);
  assert.match(css, /\.prd-placeholder-document/);
  assert.match(css, /\.prd-thinking-process/);
  assert.match(css, /\.prd-thinking-process \{[^}]*background:\s*transparent;[^}]*border:\s*0;/);
  assert.match(css, /\.prd-thinking-process > header span \{[^}]*font-size:\s*var\(--text-body-sm\);[^}]*line-height:\s*var\(--leading-body-sm\);/);
  assert.match(css, /\.prd-thinking-process li p \{[^}]*font-size:\s*var\(--text-body-sm\);[^}]*line-height:\s*var\(--leading-body-sm\);/);
  assert.match(css, /\.prd-thinking-process\.is-complete \{ background:\s*transparent; \}/);
  assert.match(css, /\.codex-choice-question \{[^}]*border: 0;/s);
  assert.match(requirements, /预览完整 PRD 文档/);
  assert.match(requirements, /const canReviewCurrentPrd = Boolean\([\s\S]*hasStartedConversation[\s\S]*!previewResetForConversation/);
  assert.match(requirements, /: draft \?\? currentArtifact\?\.content/);
  assert.doesNotMatch(requirements, /project\.stage === "REQUIREMENTS"\s*&& draft\s*&& \(!currentArtifact/);
  assert.match(requirements, /\{canReviewCurrentPrd && \(/);
  assert.doesNotMatch(requirements, /查看系统保存并用于后续流程的全部需求内容/);
  assert.match(requirements, /value\.full_document/);
  assert.doesNotMatch(requirements, /data-blueprint-step=/);
  assert.doesNotMatch(requirements, /Step 1 · 需求拆解/);
  assert.doesNotMatch(requirements, /Step 2 · 领域建模：Harness 五要素/);
  assert.doesNotMatch(requirements, /Step 3 · 组件选型/);
  assert.doesNotMatch(requirements, /Step 4 · 架构设计/);
  assert.doesNotMatch(requirements, /Step 5 · 代码生成规划/);
  assert.match(requirements, /data-prd-section="goals"/);
  assert.match(requirements, /产品目标与成功标准/);
  assert.match(requirements, /用户与使用方式/);
  assert.match(requirements, /核心业务流程/);
  assert.match(requirements, /功能与质量要求/);
  assert.match(requirements, /数据与外部依赖/);
  assert.match(requirements, /实现约束与能力需求/);
  assert.match(requirements, /产品边界与异常处理/);
  assert.match(requirements, /验收与成功指标/);
  assert.match(requirements, /待确认事项与需求追溯/);
  assert.doesNotMatch(requirements, /function FullPrdDocument[\s\S]*prdItems\(value\.core_flow/);
  assert.match(requirements, /role="dialog" aria-modal="true" aria-labelledby="full-prd-preview-title"/);
  assert.match(requirements, /该制品将用于方案、生成与部署流程/);
  assert.match(css, /\.prd-full-preview-entry \{[^}]*margin-top: 28px;[^}]*padding-left: 29px;/);
  assert.match(css, /\.prd-document-decision \{ margin-top: 32px; \}/);
  assert.match(css, /\.artifact-decision\.prd-document-decision \{ margin-top: 32px; border: 0; \}/);
  assert.match(css, /\.prd-full-preview-backdrop \{[^}]*position: fixed;[^}]*z-index: 100;/s);
  assert.match(css, /\.prd-full-preview-dialog \{[^}]*border: 0;[^}]*border-radius: var\(--radius-xxlarge\);/s);
  assert.doesNotMatch(css, /\.prd-blueprint-step-intro/);
  assert.doesNotMatch(css, /\.prd-component-selection/);
  assert.doesNotMatch(css, /\.prd-architecture-layers/);
  assert.doesNotMatch(css, /\.prd-tool-catalog/);
  assert.doesNotMatch(css, /\.prd-code-generation-plan/);
  assert.match(css, /\.artifact-decision textarea::placeholder \{ font-weight: 400; \}/);
  assert.match(css, /\.codex-choice-options > button\.selected \{[^}]*background: var\(--boss-bg-primary-light\);/);
  assert.match(css, /\.prd-typing-cursor/);
  assert.match(css, /\.prd-preview-header\.is-placeholder/);
  assert.match(css, /\.prd-structured-content/);
  assert.match(css, /\.prd-definition-rail/);
  assert.match(css, /\.prd-plan-panel/);
  assert.match(css, /\.prd-flow-list/);
  assert.match(css, /\.prd-scope-grid/);
  assert.match(css, /\.prd-notes-grid/);
  assert.match(css, /\.prd-confirmation-bar \{[^}]*flex:\s*0 0 auto;[^}]*border-top:\s*1px solid var\(--boss-border-light\)/);
  assert.match(css, /\.prd-confirmation-bar \.primary-button \{ flex:\s*0 0 auto; \}/);
  assert.match(css, /\.codex-guide-list li svg \{ justify-self:\s*center;/);
  assert.match(css, /\.codex-composer-box/);
  assert.match(css, /\.codex-model-trigger \{[^}]*background:\s*transparent/);
  assert.match(css, /\.codex-model-trigger:hover:not\(:disabled\) \{[^}]*background:\s*var\(--boss-bg-surface-hover\)/);
  assert.match(css, /\.codex-tool-button\.active \{[^}]*background:\s*var\(--boss-bg-surface-hover\)/);
  assert.match(css, /\.codex-conversation-actions > button:hover:not\(:disabled\) \{[^}]*background:\s*var\(--boss-bg-surface-hover\)/);
  assert.doesNotMatch(css, /\.codex-model-trigger\.active/);
  assert.doesNotMatch(css, /\.codex-attachment-menu|\.codex-popover-row/);
  assert.match(css, /article\.assistant > \.codex-message-content \{[^}]*background:\s*transparent/);
  assert.match(css, /article\.user > \.codex-message-content \{[^}]*background:\s*var\(--boss-bg-surface-secondary-hover\)/);
  assert.match(css, /\.codex-composer-box textarea::placeholder \{ color:\s*var\(--boss-text-quaternary\)/);
  assert.match(requirements, /disabled=\{busy && !generating\} aria-label="历史对话"/);
  assert.match(requirements, /disabled=\{busy && !generating\} aria-label="新建对话"/);
  assert.match(requirements, /item\.id !== "welcome" && item\.id !== outputStream\?\.assistantMessageId/);
  assert.doesNotMatch(requirements, /<strong title=\{conversationTitle\}>/);
  assert.match(requirements, /generationRunRef/);
  assert.match(requirements, /leaveGenerationRunningInBackground/);
  assert.doesNotMatch(requirements, /cancelGenerationForConversationNavigation/);
  assert.match(app, /workspace-progress-header/);
  assert.doesNotMatch(app, /workspace-sidebar-head/);
  assert.match(app, /boss-icon-sidecollapse/);
  assert.match(app, /boss-icon-file-cloud/);
  assert.match(app, /boss-icon-logout/);
  assert.doesNotMatch(app, /<PanelLeft|<Folder|<LogOut/);
  assert.match(css, /mask-image:\s*url\("\/hd-icon-file-cloud\.svg"\)/);
  assert.match(css, /mask-image:\s*url\("\/hd-icon-logout\.svg"\)/);
  assert.match(css, /mask-image:\s*url\("\/hd-icon-nanbeige-sidecollapse\.svg"\)/);
  assert.doesNotMatch(app, /PanelLeftOpen|PanelLeftClose|<Power/);
  assert.match(app, /project-workbench-mode/);
  assert.doesNotMatch(app, /\{isCodexWorkbench && project && \(/);
  assert.match(app, /提出点子/);
  assert.match(app, /确认方案/);
  assert.match(app, /生成预览/);
  assert.match(app, /部署上线/);
  assert.match(app, /<BossSteps/);
  assert.doesNotMatch(app, /workspace-progress-steps/);
  assert.match(stepper, /data-figma-node-id="85798:175"/);
  assert.match(stepper, /boss-step-check-outlined\.svg/);
  assert.match(stepper, /boss-step-tail-complete\.svg/);
  assert.match(stepper, /boss-step-tail-pending\.svg/);
  assert.match(stepCheck, /fill="#1C64F2"/);
  assert.match(stepCompleteTail, /stroke="#1C64F2"/);
  assert.match(stepPendingTail, /stroke-opacity="0\.12"/);
  assert.ok(historyEmpty.length > 0);
  assert.match(css, /\.boss-steps \{[\s\S]*width:\s*auto;[\s\S]*max-width:\s*calc\(100% - 36px\);[\s\S]*gap:\s*12px;/);
  assert.match(css, /\.boss-step-item \{ min-width:\s*0; flex:\s*0 0 auto; \}/);
  assert.match(css, /\.boss-step-progress \{[\s\S]*width:\s*28px;[\s\S]*height:\s*28px;/);
  assert.match(css, /\.boss-step-tail \{ width:\s*48px; min-width:\s*48px; height:\s*2px; flex:\s*0 0 48px;/);
  assert.match(css, /\.boss-step-trigger \{[\s\S]*font-size:\s*var\(--text-body-sm\);/);
  assert.match(css, /\.boss-step-progress \{[\s\S]*font-size:\s*var\(--text-body-sm\);/);
  assert.doesNotMatch(app, /workspace-progress-meta/);
  assert.match(app, /sidebarCollapsed/);
  assert.match(app, /useState<string \| null>\(null\)/);
  assert.match(app, /const sidebarCollapsed = Boolean\(projectId && expandedSidebarProjectId !== projectId\)/);
  assert.match(app, /setExpandedSidebarProjectId\(\(value\) => value === projectId \? null : projectId \?\? null\)/);
  assert.match(css, /\.workspace-layout\.project-workbench-mode/);
  assert.match(css, /grid-template-columns:\s*56px minmax\(0, 1fr\)/);
  assert.match(css, /grid-template-rows:\s*60px minmax\(0, 1fr\)/);
  assert.match(css, /\.workspace-progress-header \{[\s\S]*height:\s*60px;/);
  assert.match(css, /\.workspace-progress-header \{[\s\S]*border-bottom:\s*1px solid var\(--boss-border-light\)/);
  assert.match(tokens, /--boss-border-light:\s*#0a1b331a;/);
  assert.match(tokens, /--boss-border-sidebar-divider:\s*#0a1b330f;/);
  assert.match(css, /\.prd-assistant-pane \{ background:\s*#fff; border-right:\s*1px solid var\(--boss-border-light\); \}/);
  assert.match(css, /\.prd-pane-header \{[\s\S]*border-bottom:\s*1px solid var\(--boss-border-light\)/);
  assert.match(css, /grid-template-columns:\s*minmax\(0, 40%\) minmax\(0, 60%\)/);
  assert.match(requirements, /solution-decision-view/);
  assert.match(requirements, /solution-whitebox-view/);
  assert.match(requirements, /先做一个能完整跑通核心任务的首版/);
  assert.match(requirements, /页面底部点击“方案没问题，开始生成产品”即可进入下一步/);
  assert.match(requirements, /数据保存在当前设备的浏览器里/);
  for (const section of [
    "用户会怎样完成目标",
    "首版包含什么",
    "这批功能以后再决定",
    "首版页面与功能",
    "AI 在产品里做什么",
    "数据怎么保存",
    "费用怎么算",
    "需要什么账号或授权",
    "你需要提前知道的限制",
    "你最终会拿到什么",
    "工厂在背后怎样保障",
  ]) assert.match(requirements, new RegExp(section));
  assert.match(requirements, /prdContent=\{latestPrd\?\.content \?\? \{\}\}/);
  assert.match(requirements, /按意见更新方案/);
  assert.doesNotMatch(requirements, /本页不再重复需求和功能范围/);
  assert.match(css, /\.solution-recommendation-card/);
  assert.match(css, /\.solution-fact-grid/);
  assert.match(css, /\.solution-user-flow/);
  assert.match(css, /\.solution-scope-overview/);
  assert.match(css, /\.solution-insight-grid/);
  assert.match(css, /\.solution-safeguard-grid/);
  assert.match(development, /implementation-details technical-evidence/);
  assert.match(development, /工厂正在把方案变成真实产品/);
  assert.match(development, /真实生成状态/);
  assert.match(development, /UiStylePicker/);
  assert.match(development, /生成 HTML 网页/);
  assert.match(development, /前端 HTML 文件已生成/);
  assert.match(development, /打开可交互 HTML 网页/);
  assert.match(uiStyles, /Slack/);
  assert.match(uiStyles, /Pirsch/);
  assert.match(uiStyles, /Aira/);
  assert.match(uiStyles, /Atlassian/);
  assert.match(uiStyles, /Ameba/);
  assert.match(uiStyles, /Sprout/);
  assert.match(uiStyles, /Surfshark/);
  assert.match(uiStyles, /Pop Site/);
  assert.match(development, /item as Record<string, unknown>/);
  assert.doesNotMatch(development, /String\(item\)/);
  assert.match(preview, /loadUiStylePreference/);
  assert.match(preview, /runUiStyle/);
  assert.match(preview, /api\.startDevelopment\(project\.id, desiredStyleKey\)/);
  assert.match(preview, /build-preview-loading/);
  assert.match(preview, /generated-html-frame/);
  assert.match(preview, /完成后会自动打开可交互预览/);
  assert.match(preview, /api\.acceptPreview/);
  assert.doesNotMatch(preview, /我在介绍项目时说得太散/);
  assert.match(usage, /真实 AI 调用/);
  assert.match(usage, /当前记录全部来自体验模式/);
  assert.match(usage, /item\.source !== "mock"/);
  assert.match(deployment, /api\.capabilities\(\)/);
  assert.match(deployment, /api\.cloudCredentials\(project\.id\)/);
  assert.match(deployment, /api\.deploymentAuthorizations\(project\.id\)/);
  assert.match(deployment, /只完成发布演练，没有创建线上资源/);
  assert.match(deployment, /deployment-assistant-pane/);
  assert.match(deployment, /deployment-process-pane/);
  assert.match(deployment, /AI Agent 产品上线部署手册/);
  assert.match(app, /project\?\.preview_accepted/);
  assert.doesNotMatch(deployment, /Access Key ID|Secret Access Key/);
  assert.match(delivery, /真实 GitHub 同步尚未启用/);
  assert.match(delivery, /item\.status === "succeeded" && Boolean\(item\.deployment_url\)/);
  assert.match(css, /\.reality-status-card/);
  assert.match(css, /\.quality-truth-note/);
  assert.match(css, /\.build-preview-loading/);
  assert.match(css, /@keyframes build-orbit-spin/);
  assert.match(app, /window\.scrollTo\(\{ top: 0, left: 0, behavior: "auto" \}\)/);
  assert.match(css, /--blue:\s*var\(--boss-bg-primary\)/);
  assert.match(css, /--canvas:\s*var\(--boss-bg-light\)/);
  assert.match(css, /\.sidebar-create-project \{[^}]*background:\s*var\(--color-royal-signal\)[^}]*box-shadow:\s*none/);
  assert.match(css, /\.sidebar-brand \.brand-mark/);
  assert.doesNotMatch(css, /\.sidebar-create-project \{[^}]*linear-gradient/);
  assert.match(css, /\.sidebar-account \.user-avatar \{[^}]*background:\s*var\(--color-codex-avatar\)/);
  assert.match(css, /\.sidebar-account \.sidebar-profile \{ width: 100%/);
  assert.match(tokens, /--page-max-width:\s*1200px/);
  assert.match(tokens, /--text-body-sm:\s*14px/);
  assert.match(tokens, /--boss-bg-primary:\s*#1c64f2/);
  assert.match(tokens, /--boss-bg-primary-hover:\s*#1959d8/);
  assert.match(tokens, /--boss-text-base:\s*#0a1b33/);
  assert.match(tokens, /--boss-border-input:\s*#e1e3e6/);
  assert.match(tokens, /--control-height-default:\s*32px/);
  assert.match(tokens, /--control-height-large:\s*40px/);
  assert.match(tokens, /--sidebar-width:\s*200px/);
  assert.match(tokens, /--leading-body-sm:\s*22px/);
  assert.match(tokens, /--color-royal-signal:\s*var\(--boss-bg-primary\)/);
  assert.match(tokens, /--color-codex-avatar:\s*#b49a62/);
  assert.match(css, /BOSS Design System · Light mode normalization/);
  assert.match(css, /\.workspace-layout \.primary-button \{[^}]*background:\s*var\(--boss-bg-primary\)/);
  assert.match(css, /\.workspace-layout \.ghost-button \{[^}]*border:\s*1px solid var\(--boss-border-base\)/);
  assert.match(css, /\.sidebar-account button\[aria-label="退出登录"\] \{ color:\s*var\(--boss-icon-light\)/);
  assert.match(css, /\.sidebar-brand \.brand-mark \{ width:\s*32px; height:\s*32px/);
  assert.match(app, /className="dot-logo-glyph"/);
  assert.match(css, /\.sidebar-brand \.dot-logo-glyph \{[\s\S]*width:\s*44px;[\s\S]*height:\s*44px;[\s\S]*scale\(\.7272727\)/);
  assert.match(app, /className="sidebar-brand" aria-label="点线面"[\s\S]*<span><strong>点线面<\/strong><\/span>/);
  assert.match(app, /className="sidebar-brand-row"[\s\S]*className="sidebar-brand"[\s\S]*className="workspace-nav-toggle"/);
  assert.match(css, /\.project-workbench-mode \.factory-sidebar \{[\s\S]*grid-row:\s*1 \/ 3;/);
  assert.match(css, /\.project-workbench-mode\.sidebar-expanded \.factory-sidebar \{ padding:\s*20px 16px 14px; \}/);
  assert.match(css, /\.project-workbench-mode:not\(\.sidebar-expanded\) \.sidebar-brand-row \.sidebar-brand > span:last-child \{ display:\s*none; \}/);
  assert.match(css, /\.project-workbench-mode:not\(\.sidebar-expanded\) \.sidebar-create-project \{[\s\S]*display:\s*flex;[\s\S]*align-items:\s*center;[\s\S]*justify-content:\s*center;/);
  assert.match(css, /\.project-workbench-mode:not\(\.sidebar-expanded\) \.sidebar-footer \{ display:\s*block; \}/);
  assert.match(css, /\.workspace-nav-toggle \{[\s\S]*width:\s*32px;[\s\S]*height:\s*32px;/);
  assert.match(css, /\.project-workbench-mode \.factory-sidebar \{ border-right:\s*1px solid var\(--boss-border-sidebar-divider\)/);
  assert.match(css, /\.boss-icon-logout \{ width:\s*16px; height:\s*16px;/);
  assert.match(css, /\.boss-icon-sidecollapse \{ width:\s*16px; height:\s*16px;/);
  assert.match(css, /\.sidebar-project-item\.selected,[\s\S]*background:\s*var\(--boss-bg-surface-active\)/);
  assert.match(css, /\.factory-sidebar \.sidebar-create-project \{ width:\s*100%; margin:\s*0; \}/);
  assert.match(css, /\.factory-sidebar \.sidebar-brand-row \{ padding:\s*0 0 var\(--space-250\); \}/);
  assert.match(css, /\.inline-create-project\.create-project-dialog \{ border-radius: var\(--radius-xxlarge\); \}/);
  assert.match(tokens, /--radius-xxlarge:\s*16px;/);
  assert.match(css, /\.factory-sidebar \.sidebar-project-list \{ padding:\s*0; \}/);
  assert.match(css, /\.sidebar-project-list\.empty \{[^}]*grid-template-rows:\s*auto minmax\(0, 1fr\)/);
  assert.match(css, /\.sidebar-project-empty > \.sidebar-project-empty-art \{[\s\S]*history-record-empty\.png/);
  assert.match(css, /\.factory-sidebar \.sidebar-footer,[\s\S]*\.factory-sidebar \.sidebar-profile \{ padding:\s*0; \}/);
  assert.match(css, /\.sidebar-project-row:is\(:hover, :focus-within\) \.sidebar-project-delete/);
  assert.match(css, /prefers-reduced-motion/);
  assert.doesNotMatch(css, /\.login-story::after[\s\S]*radial-gradient/);
  assert.match(css, /\.login-layout \{[^}]*background:\s*linear-gradient\(180deg, #a9ccff 0%, #bad7ff 10%, #d2e6ff 20%, #e5f1ff 50%, #f4f9ff 80%, #ffffff 100%\)/);
  assert.doesNotMatch(css, /\.login-layout \{[^}]*var\(--boss-bg-primary-light-active\)/);
  const workspaceComplianceStart = css.indexOf("/* Logged-in product UI compliance layer.");
  const workspaceComplianceEnd = css.indexOf(
    "/* End logged-in product UI compliance layer. */",
    workspaceComplianceStart,
  );
  const workspaceCompliance = css.slice(workspaceComplianceStart, workspaceComplianceEnd);
  assert.match(workspaceCompliance, /\.workspace-layout :is\(\.primary-button, \.ghost-button\)/);
  assert.match(workspaceCompliance, /\.workspace-layout \.status-pill\.success i/);
  assert.match(workspaceCompliance, /\.workspace-layout \.create-guide-card \{ animation: none; \}/);
  assert.match(css, /\.sidebar-project-item\.selected/);
  assert.match(css, /\.workspace-layout \.phase-view-tabs/);
  assert.match(css, /\.workspace-layout \.implementation-details/);
  assert.match(css, /\.workspace-layout \.segment-progress \{ grid-template-columns: repeat\(4, 1fr\)/);
  assert.doesNotMatch(workspaceCompliance, /\.login-(layout|story|panel|benefit)/);
  assert.match(app, /使用 GPT 账号登录/);
  assert.match(app, /api\.startCodexLogin/);
  assert.match(app, /api\.codexLoginStatus/);
  assert.doesNotMatch(app, /\/signin-with-chatgpt\?return_to=%2F/);
  assert.doesNotMatch(app, /请输入账号名称|请输入邀请码/);
  assert.match(css, /\.gpt-login-button/);
  assert.match(packageJson, /lucide-react/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
});
