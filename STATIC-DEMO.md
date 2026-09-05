# 原版点线面 UI · 柠檬项目 Demo

本版直接编译 `demo-source` 正在运行的 React 组件和原样式。没有另外重画页面。上一版独立编写的 Demo 页面已由本版替换。

## 原版 UI 与内置数据

- 原版 ProductFactoryApp、BossSteps 和 StagePanels。
- 第一步使用 M1ARequirements，加载柠檬历史对话、原始 PRD，保留完整文档弹窗、模拟对话和历史切换。
- 第二步使用 SolutionVisualDecisionView，保留低保真原型、原有五个界面、真实按钮状态和八种风格选择。
- 第三步使用 M1DPreview，保留生成进度、重新生成、产品 iframe、验收和进入部署。
- 第四步使用 M2BDeployment，保留原有上线助手、历史对话、七步导航、第 6 次发布记录和结果缩览。

只有数据接口换成 `demo-source/static-demo/client.ts` 中的浏览器模拟接口。原 API 客户端不进入 Demo 构建。初始化采用 `seed.json` 中的安全案例数据，任何生成、账号连接和发布动作都不会调用真实服务。预览 iframe 使用柠檬原项目的浏览器版。

## Demo 适配

静态构建使用同一份源组件；构建时将图片路径改成相对地址，替代 Next Image 为普通图片，允许已完成案例重新打开原有需求对话和确认入口，保留预置上线对话。无需填写真实凭证，演示连接使用内置占位值。角落有 Demo 标记和重置入口。上述适配只应用于静态构建，不改变 localhost:3000 的运行行为。

首次进入体验页会显示 Demo 欢迎弹窗，说明通过已完成的柠檬项目了解四步流程；同一标签页关闭后不重复显示，可点击右上角 Demo 标记重新查看，重置案例后再次显示。第四步始终显示打勾和“已完成”，可继续点击查看或模拟部署过程。

选择风格会演示原选择及生成流程；预设产物仍是柠檬案例（深色原版或浅色演示变体），不为任意需求真正生成代码。

`site/demo/ui-source-manifest.json` 记录编译所用原版组件和 CSS 的 SHA-256，便于核对 UI 来源。

## 构建与验收

在 `demo-source` 目录运行：

```sh
npm run build
npm run typecheck
```

输出到仓库的 `site/demo/`。在仓库根目录运行：

```sh
python3 -m http.server 8086 --directory site
node --test scripts/test-static-demo.mjs
```

浏览器已验证原版四阶段、原型点击、完整 PRD 弹窗、历史切换、新建对话选项、模拟生成、验收进入部署、七步导航、手机布局及无真实 API 请求。

## 发布

`site/` 是完整静态产物，展示页的三个立即体验链接均指向 `./demo/`。上传包包含这个目录和 `.github/workflows/pages.yml`。GitHub Settings → Pages → Source 选择 GitHub Actions，然后运行工作流即可。

只发布静态产物即可，无需发布源码、安装数据库或部署后端。无登录、AI 调用或云资源创建费用。公开体验入口为 README 中的 GitHub Pages 链接。

数据只保存在访客浏览器内，重置案例会恢复柠檬的原始展示状态。没有复制原始数据库、Codex 授权、用户会话、云密钥或真实部署地址。
