# AI 产品工厂后端｜第八阶段 M3/M4

## 启动

```bash
cd '/Users/apple/Downloads/个人项目/产品工厂 Agent/后端第八阶段/backend'
python3.11 -m venv .venv
.venv/bin/pip install -e . --group dev
test -f .env || cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8018
```

本阶段不新增 Web 测试入口。API 文档仅开发环境在 `http://127.0.0.1:8018/docs`。

## 生产秘密配置

`CREDENTIAL_MASTER_KEY` 必须是解码后恰好 32 字节的 URL-safe base64 随机值，并通过生产 Secret 注入。不要提交 `.env`。更换主密钥前必须执行凭证轮换流程，否则旧密文无法解密。

模型价格由 `AI_INPUT_COST_MICROUSD_PER_MILLION` 和 `AI_OUTPUT_COST_MICROUSD_PER_MILLION` 配置；未配置时 API 明确标为不可用，不虚构金额。

## 验证

```bash
.venv/bin/ruff check app alembic tests
.venv/bin/python -m compileall -q app alembic tests
.venv/bin/pytest -q
.venv/bin/alembic current
.venv/bin/alembic check
```

迁移头：`20260821_0008`。生产使用 PostgreSQL 与受信任外部备份适配器。

当前全量自动化结果：`75 passed`。
