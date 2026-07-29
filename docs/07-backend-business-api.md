# 7. FastAPI 业务层实现

## 7.1 分层约定

每个领域模块独立包含：

```text
app/modules/<domain>/
├─ router.py       # HTTP 路径、状态码、Schema、依赖注入
├─ schemas.py      # Pydantic 请求与响应契约
├─ service.py      # 业务规则、事务、幂等与跨资源编排
└─ repository.py  # SQLAlchemy 查询和持久化
```

Router 不直接查询数据库，不直接调用 Dify，也不计算报价或评分。Service 持有用例逻辑，Repository 只封装数据访问。

## 7.2 REST 接口

公网由 Nginx 同源代理，以下路径均以 `/api/v1` 为前缀。

| 方法 | 路径 | 权限 | 主要行为 |
|---|---|---|---|
| POST | `/auth/login` | Public | 多租户登录并签发 24 小时 JWT 与 Refresh Token |
| POST | `/auth/refresh` | Refresh Token | 轮换 Refresh Token 并签发新 JWT |
| POST | `/auth/logout` | Refresh Token | 撤销当前 Refresh Token |
| GET | `/customers` | `customer.read_*` | 租户隔离客户列表 |
| POST | `/customers` | `customer.create` | 创建并默认分配给当前销售 |
| POST | `/conversation/message` | `message.send` | 幂等写消息并创建 Connector Outbox |
| POST | `/agent/chat` | `ai_agent.chat` | 调用 Dify、记录 AI Run、生成回复与 Outbox |
| POST | `/lead-score` | `customer.score` | 可解释规则评分并更新客户意向 |
| POST | `/quotation` | `quotation.create` | 服务端重算报价金额并创建草稿 |
| GET | `/connectors` | `connector.read/manage` | 返回连接器及健康状态，不返回密钥 |
| POST | `/connectors/config` | `connector.secret_manage` | AES-256-GCM 加密写入配置 |
| POST | `/notifications/send` | `notification.send` | 幂等创建通知与投递 Outbox |

## 7.3 认证

登录请求：

```json
{
  "tenant_slug": "acme-export",
  "email": "sales@example.com",
  "password": "a-strong-password"
}
```

邮箱只在租户内唯一，因此登录必须提供 `tenant_slug`。密码用 Argon2id 校验；Access Token
包含用户和租户公共 ID、issuer、audience、签发时间和过期时间，默认有效期 24 小时。
Refresh Token 默认有效 30 天，数据库只保存哈希且每次刷新都会轮换。每个受保护请求都会
重新从数据库解析有效用户、有效租户和 RBAC 权限。

生产必须配置至少 32 个随机字符的 `JWT_SECRET`。Token 和 Dify API Key 不进入前端构建变量。

## 7.4 客户

`GET /customers` 支持 `limit`、`offset`、`search` 和 `lifecycle_stage`。拥有 `customer.read_all` 才能读取全部租户客户；当前数据库没有团队实体，因此 `read_own/read_team` 暂时都收敛到当前销售名下，避免越权。

`POST /customers` 规范化邮箱和国家代码，新客户默认分配给当前用户。

## 7.5 聊天

人工消息请求必须提供 `idempotency_key`。Service：

1. 按租户锁定 Conversation。
2. 检查状态和幂等键。
3. 在锁内生成 `sequence_no`，保证会话消息顺序。
4. 创建 `messages` 记录。
5. 同事务创建 `connector.message.send.requested.v1` Outbox。
6. 返回 `202 Accepted`，由 Worker 完成真实渠道发送。

## 7.6 Dify Agent

请求示例：

```json
{
  "conversation_id": "01J...",
  "query": "We need 500 units delivered to Germany.",
  "idempotency_key": "web-request-20260724-001",
  "inputs": {
    "language": "en"
  }
}
```

Service 先持久化触发消息和 `ai_agent_runs`，再在数据库事务之外调用 Dify blocking Chat API。成功后重新锁定会话、保存 AI 输出消息、Token/成本/引用和 Dify 会话映射，并创建 Connector Outbox。失败则把 AI Run 标记为 `failed`，不会丢失客户输入。

平台使用自己的客户公共 ID 构造 Dify `user`，Dify API Key 仅存在于后端 `.env`。

## 7.7 Lead Score

首个评分版本为 `rules-v1`，维度与权重：

- 需求明确度：25%
- 预算匹配：20%
- 紧迫度：20%
- 互动度：15%
- 客户画像匹配：20%

每个输入范围为 0–100。Service 保存总分、等级、权重、分项和评分版本，确保结果可解释。等级为 `hot/warm/nurture/cold`。

## 7.8 Quotation

报价支持产品项和临时手工项。Service 会：

- 验证客户、会话和产品均属于当前租户
- 验证会话客户一致
- 验证产品币种和最小起订量
- 使用 `Decimal(19,4)` 重新计算小计、折扣、税费、运费和总额
- 保存产品 SKU、名称和价格快照
- 创建 `draft` 报价，正式发送和审批由后续状态接口处理

客户端提交的汇总金额不被接受。

## 7.9 Connector 配置

配置值全部使用 AES-256-GCM 加密，即使 `is_secret=false` 也不以明文落库。关联数据绑定租户、连接器和配置 Key，防止密文被复制到其他配置位置后仍可解密。

`CONFIG_ENCRYPTION_KEY` 必须是 32 个随机字节的 URL-safe Base64，Key 版本保存到 `connector_configs.key_version`，为后续轮换预留。

## 7.10 Notification

通知接口仅创建 `notifications` 和 `notification.requested.v1` Outbox，返回 `202 Accepted`。Worker/n8n 承担邮件、IM 或其他外部投递。传入 `dedupe_key` 时，重复请求返回原通知，不会重复创建。

## 7.11 错误格式

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Customer was not found.",
    "details": [],
    "request_id": "optional-request-id"
  }
}
```

业务异常统一映射为 401、403、404、409、502 或 503，不向客户端返回 SQL、堆栈或上游密钥。

## 7.12 启动

在数据库迁移完成且 `.env` 已配置后：

```bash
cd backend
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

开发环境 OpenAPI 位于 `/docs`；生产环境自动关闭 `/docs`、`/redoc` 和 `/openapi.json`。
