# WhatsApp Business API Connector

本 Connector 使用 WhatsApp Cloud API，并复用平台现有的多租户 Connector、
AES-GCM 配置加密、Customer、Conversation、Message、AI Agent Run 和 WebhookLog
模型。无需修改数据库结构。

## 配置项

在后台“Connector 管理”中配置 WhatsApp：

| 配置 | 用途 | API 是否返回明文 |
| --- | --- | --- |
| `phone_number_id` | Cloud API 发信号码 ID、Webhook 租户路由 | 否 |
| `business_account_id` | 校验 Webhook 所属 WABA | 否 |
| `access_token` | 调用 Graph API | 否 |
| `verify_token` | Meta Webhook GET 验证 | 否 |
| `app_secret` | 校验 POST 的 `X-Hub-Signature-256` | 否 |

`access_token`、`verify_token` 和 `app_secret` 强制作为敏感配置保存。配置状态接口
只返回已配置的键名，绝不返回值。建议使用具有
`whatsapp_business_messaging` 权限的长期 System User Token。

保存配置后调用“测试连接”，成功后 Connector 状态才会切换为 `active`：

```text
POST /api/v1/connectors/whatsapp/test
{"connector_id": "<CONNECTOR_PUBLIC_ID>"}
```

## Meta Webhook

Callback URL：

```text
https://YOUR_DOMAIN/api/v1/webhooks/whatsapp
```

验证和接收共用该地址：

```text
GET  /api/v1/webhooks/whatsapp
POST /api/v1/webhooks/whatsapp
```

GET 使用 Connector 中加密保存的 `verify_token` 返回 challenge。POST 按以下顺序处理：

1. 从 payload 的 `phone_number_id` 定位租户和 active Connector。
2. 校验 payload 的 WABA ID。
3. 使用 `app_secret` 验证原始请求体的 HMAC-SHA256 签名。
4. 以 WhatsApp message ID 做幂等处理并写入脱敏 `WebhookLog`。
5. 创建或查询 Customer、CustomerSession 和 open Conversation。
6. 保存 inbound Message 和 `AiAgentRun`。
7. 调用 Dify，保存 outbound Message。
8. 调用 `/{phone_number_id}/messages` 发送文本回复并回写 provider message ID。

日志不记录消息正文、Access Token、Verify Token 或 App Secret。

## Docker 配置

`.env` 可配置：

```dotenv
WHATSAPP_GRAPH_API_BASE_URL=https://graph.facebook.com
WHATSAPP_GRAPH_API_VERSION=v23.0
WHATSAPP_TIMEOUT_SECONDS=15
WHATSAPP_PROCESSING_TIMEOUT_SECONDS=60
WHATSAPP_WEBHOOK_MAX_BYTES=1048576
```

Graph API 版本显式固定，升级前应在测试环境验证。部署：

```bash
docker compose up -d --build
docker compose config
docker compose ps
docker compose logs --tail=200 backend
```

容器需要能够访问 `graph.facebook.com` 和 Dify API。Nginx 已将 `/api/` 转发到
Backend，不需要新增公网端口。

## 验收建议

1. 后台保存五项配置，确认浏览器 Network 响应中没有任何密钥值。
2. 测试连接成功，Connector 变为 `active/healthy`。
3. 在 Meta 控制台完成 Callback URL 和 Verify Token 验证。
4. 从真实 WhatsApp 号码发送一条测试消息。
5. 检查客户、会话和两条 Message（inbound/outbound）。
6. 检查 `webhook_logs` 为 `processed` 且 payload 已脱敏。
7. 重放相同 webhook，确认不会重复调用 Dify 或重复创建消息。
