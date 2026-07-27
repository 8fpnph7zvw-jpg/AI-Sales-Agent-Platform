# OpenWA WhatsApp Connector

本项目通过独立的 OpenWA 微服务接入 WhatsApp。OpenWA 源码以 Git submodule
固定在 `services/openwa`，不复制到 Backend；FastAPI 只通过 HTTP API 与其通信。

## 架构

```text
WhatsApp
  -> OpenWA
  -> POST /api/v1/webhooks/whatsapp
  -> FastAPI（租户、幂等、会话、消息落库）
  -> Dify Agent / RAG
  -> OpenWA send-text
  -> WhatsApp
```

`backend` 和 `openwa` 同时加入 `connector_net`。容器内访问地址为
`http://openwa:2785/api`，不经过宿主机端口或 Nginx。

## 环境变量

OpenWA 首次启动不需要预先提供 API Key。以下三个值由 `openwa-init`
自动生成或补全：

```dotenv
OPENWA_URL=http://openwa:2785/api
OPENWA_API_KEY=
OPENWA_SESSION=
OPENWA_SESSION_NAME=ai-sales-agent
OPENWA_PORT=2785
OPENWA_ENGINE_TYPE=whatsapp-web.js
```

`OPENWA_SESSION_NAME` 是稳定的人类可读名称；`OPENWA_SESSION` 是 OpenWA
创建后返回的真实 UUID。不要提前填充 `OPENWA_API_KEY` 或使用
`ALLOW_DEV_API_KEY`、`dev-admin-key`、测试密钥。真实 `.env` 不提交到 Git。

## 启动

```bash
git submodule update --init --recursive
cp .env.example .env
# 按现有项目要求配置 MySQL、Redis、JWT 等非 OpenWA 配置。
# OPENWA_API_KEY 和 OPENWA_SESSION 保持为空。
docker compose up -d
docker compose ps -a
```

Windows PowerShell 可使用：

```powershell
git submodule update --init --recursive
Copy-Item .env.example .env
docker compose up -d
docker compose ps -a
```

首次启动顺序：

1. `openwa` 在没有 `API_MASTER_KEY` 的情况下启动。
2. OpenWA 使用密码学安全随机数生成 `owa_k1_...` 管理密钥，并保存到
   `/app/data/.api-key`。
3. 一次性 `openwa-init` 服务读取并调用 `/api/auth/validate` 验证该密钥。
4. `openwa-init` 查找或创建 `OPENWA_SESSION_NAME` 对应的 Session，取得真实 UUID。
5. `openwa-init` 自动创建或更新 Backend Webhook，HMAC secret 使用真实密钥。
6. 密钥和 Session UUID 写入隔离的 `openwa_runtime` 卷，同时安全更新项目 `.env`。
7. `backend` 等待初始化成功，从运行时卷读取两个值并导出为
   `OPENWA_API_KEY`、`OPENWA_SESSION` 后启动。

OpenWA Dashboard 和 Swagger：

- Dashboard: `http://127.0.0.1:2785`
- Swagger: `http://127.0.0.1:2785/api/docs`

## 连接 OpenWA Session

Session 已由 `openwa-init` 自动创建。进入 Dashboard，启动
`ai-sales-agent` Session 并扫描 QR；状态应变为 `ready`。真实 Session UUID
已自动写入 `.env` 的 `OPENWA_SESSION`。

## 注册 Webhook

OpenWA 在 Docker 网络中直接回调 Backend。`openwa-init` 自动注册或更新：

- URL：`http://backend:8000/api/v1/webhooks/whatsapp`
- Event：`message.received`
- HMAC secret：自动生成的真实 OpenWA API Key

FastAPI 使用运行时注入的同一密钥校验 `X-OpenWA-Signature`。Compose 已设置
`SSRF_ALLOWED_HOSTS=backend`，不需要手工复制密钥或注册 Webhook。

## 配置平台 Connector

在管理后台的 Connector 页面填写 `OpenWA Session ID` 并执行连接测试；
也可以使用 API：

```bash
curl -X POST http://localhost/api/v1/connectors/config \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "connector_id":"YOUR_CONNECTOR_ID",
    "values":[
      {"key":"session_id","value":"OPENWA_SESSION中的UUID","value_type":"string","is_secret":false}
    ]
  }'

```

在管理后台执行现有连接检查后 Connector 变为 `active`。Webhook 使用 `sessionId` 定位对应租户，
因此一个 OpenWA Session 只能绑定到一个激活的租户 Connector。

## 发送消息接口

`POST /api/v1/whatsapp/send` 保留现有 JWT 和权限体系，调用者必须拥有
`message.send` 或 `connector.manage` 权限。

```bash
curl -X POST http://localhost/api/v1/whatsapp/send \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"recipient":"15551234567","text":"Hello from AI Sales Agent"}'
```

手机号会规范化为 OpenWA 所需的 `<digits>@c.us`；也可以直接传入
`@c.us` 或 `@g.us` Chat ID。

## 验收

```bash
docker compose logs --tail=200 openwa backend
docker compose logs --tail=100 openwa-init
docker compose ps -a
curl http://127.0.0.1:2785/api/health/ready
curl http://localhost/health/live
```

从真实 WhatsApp 号码向已连接号码发送消息后，应看到：

1. OpenWA 投递 `message.received` Webhook。
2. FastAPI 验签并按 OpenWA idempotency key 去重。
3. Customer、CustomerSession、Conversation、Inbound Message 和 WebhookLog 落库。
4. FastAPI 调用 Dify；Dify 使用现有知识库/RAG 生成回答。
5. Outbound Message 落库并通过 OpenWA 回复，状态更新为 `sent`。

OpenWA 使用非官方 WhatsApp 客户端，存在账号限制或封禁风险。生产环境应使用
独立、可承受损失且已获用户同意的号码，并控制发送频率；合规或关键业务优先考虑
Meta 官方 WhatsApp Cloud API。
