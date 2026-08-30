# 点线面 Web 工作台

面向非技术产品创造者的八阶段产品开发工作台。页面用普通语言解释“现在发生了什么、需要你决定什么”，技术名词、代码与后端状态仍保持真实。

## 本地体验

需要两个终端窗口，先启动第八阶段累计后端，再启动 Web 页面。

### 1. 启动后端

```bash
cd "../后端第八阶段/backend"
mkdir -p data/workspaces data/secrets data/deliveries data/backups
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8018
```

### 2. 启动前端

```bash
cd "../product-factory-web"
npm install
npm run dev
```

浏览器打开 `http://localhost:3000`。本地开发登录码是 `local-development-invite`，它只用于当前电脑的开发体验，正式上线前必须替换。

## 后端连接方式

前端默认连接 `http://localhost:8018/api/v1`。如后端地址不同，复制 `.env.example` 为 `.env.local` 并修改 `NEXT_PUBLIC_API_BASE_URL`。

第八阶段后端是累计版本，包含 M1A 至 M3/M4 的完整接口；前七个独立阶段目录不被覆盖，仍可分别回归和修复。

## 质量检查

```bash
npm run lint
npm run typecheck
npm test
```

更多说明见：

- `docs/八阶段前端开发文档.md`
- `docs/前端技术适配声明.md`
