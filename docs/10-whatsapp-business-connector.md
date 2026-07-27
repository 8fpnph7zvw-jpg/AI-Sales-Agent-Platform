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

复制 `.env.example` 为 `.env`，并至少修改以下值：

```dotenv
OPENWA_URL=http://openwa:2785/api
OPENWA_API_KEY=replace-with-a-strong-openwa-api-key
OPENWA_SESSION=ai-sales-agent
OPENWA_PORT=2785
OPENWA_ENGINE_TYPE=whatsapp-web.js
```

`OPENWA_API_KEY` 同时作为 OpenWA `API_MASTER_KEY` 和 Webhook HMAC secret。
不要把真实 `.env` 提交到 Git。

## 启动

```bash
git submodule update --init --recursive
cp .env.example .env
# 编辑 .env 中所有必填密码、密钥和 OpenWA 配置
docker compose up -d --build
docker compose ps
```

Windows PowerShell 可使用：

```powershell
git submodule update --init --recursive
Copy-Item .env.example .env
docker compose up -d --build
```

OpenWA Dashboard 和 Swagger：

- Dashboard: `http://127.0.0.1:2785`
- Swagger: `http://127.0.0.1:2785/api/docs`

## 创建并连接 OpenWA Session

以下请求直接访问 OpenWA。`OPENWA_SESSION`、创建 Session 时的 `name`，
以及平台 Connector 的 `session_id` 必须完全一致。

```bash
curl -X POST http://127.0.0.1:2785/api/sessions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $OPENWA_API_KEY" \
  -d '{"name":"ai-sales-agent"}'

curl -X POST http://127.0.0.1:2785/api/sessions/ai-sales-agent/start \
  -H "X-API-Key: $OPENWA_API_KEY"

curl http://127.0.0.1:2785/api/sessions/ai-sales-agent/qr \
  -H "X-API-Key: $OPENWA_API_KEY"
```

扫描 QR 后，Session 状态应变为 `ready`。

## 注册 Webhook

OpenWA 在 Docker 网络中直接回调 Backend。必须设置 `secret`，其值与
`OPENWA_API_KEY` 相同；FastAPI 会验证原始请求体上的
`X-OpenWA-Signature`。

```bash
curl -X POST http://127.0.0.1:2785/api/sessions/ai-sales-agent/webhooks \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $OPENWA_API_KEY" \
  -d '{
    "url":"http://backend:8000/api/v1/webhooks/whatsapp",
    "events":["message.received"],
    "secret":"YOUR_OPENWA_API_KEY"
  }'
```

Compose 已设置 `SSRF_ALLOWED_HOSTS=backend`，允许 OpenWA 注册该内部地址。

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
      {"key":"session_id","value":"ai-sales-agent","value_type":"string","is_secret":false}
    ]
  }'

curl -X POST http://localhost/api/v1/connectors/whatsapp/test \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"connector_id":"YOUR_CONNECTOR_ID"}'
```

测试成功后 Connector 变为 `active`。Webhook 使用 `sessionId` 定位对应租户，
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
