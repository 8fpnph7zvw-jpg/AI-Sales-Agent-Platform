# WhatsApp Business Connector

WhatsApp 渠道通过统一 Connector 接口接入，FastAPI 核心业务不依赖具体 provider runtime。

```text
FastAPI business services
  -> WhatsAppConnector
    -> WhatsAppProviderAdapter
      -> WhatsApp Cloud API (built-in)
      -> whatsapp-web.js gateway (built-in)
      -> future Baileys adapter
      -> future provider adapters
```

## 当前 Provider

内置 `cloud_api` 和 `webjs_gateway` 两个 adapter。Cloud API 的 Graph API 地址和版本由服务端环境变量管理：

```dotenv
WHATSAPP_GRAPH_API_BASE_URL=https://graph.facebook.com
WHATSAPP_GRAPH_API_VERSION=v23.0
WHATSAPP_TIMEOUT_SECONDS=15
WHATSAPP_PROCESSING_TIMEOUT_SECONDS=60
WHATSAPP_WEBHOOK_MAX_BYTES=1048576
```

每个租户 Connector 的以下凭据通过后台加密保存：

- `phone_number_id`
- `access_token`
- `verify_token`
- `app_secret`
- `adapter`（`cloud_api` 或 `webjs_gateway`）

WhatsApp Web 模式仅保存 `adapter=webjs_gateway` 和 `session_id`。Gateway URL 与
共享密钥只存在于服务端环境变量中；浏览器通过 FastAPI 的
`/connectors/whatsapp/{id}/web-session/*` 接口管理二维码会话，不直接访问 Node gateway。

## Webhook

每个 Connector 使用独立回调地址：

```text
POST /api/v1/webhooks/whatsapp/{connector_id}
GET  /api/v1/webhooks/whatsapp/{connector_id}
```

GET 路由处理 Meta webhook 订阅 challenge。POST 路由使用 `X-Hub-Signature-256`
和 Connector 的 App Secret 验签，再把 provider payload 转换为
`UnifiedMessageEnvelope`。

## 消息处理

1. Provider adapter 验签并标准化入站消息。
2. FastAPI 按 provider message ID 去重并记录脱敏 webhook 日志。
3. 消息写入既有 Customer、Conversation 和 Message 业务表。
4. Dify Agent 生成回复。
5. 回复通过同一个 provider adapter 发送并更新消息状态。

## 新增 Provider

新增实现应继承 `WhatsAppProviderAdapter`，实现配置校验、健康检查、Webhook
challenge、入站标准化和发送方法，然后注册到 `whatsapp_provider_registry`。
核心 Conversation、Dify、RAG 和数据库业务不需要随 provider 改动。
