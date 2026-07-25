# 5. API 设计

## 5.1 API 边界

- 浏览器基地址：`https://<domain>/api/v1`
- 渠道 webhook：`https://<domain>/hooks/v1`
- 内部自动化：仅 Docker 内网的 `/internal/v1`，不经公网 Nginx 暴露
- Content-Type：`application/json; charset=utf-8`
- 文件上传：推荐预签名上传；小文件管理接口可使用 `multipart/form-data`
- API 文档：非生产环境提供 OpenAPI；生产仅在受控运维环境提供

资源路径使用复数名词和 kebab-case；API 只暴露 `public_id`，不暴露自增主键。

## 5.2 认证与会话

推荐模式：

- Access Token：短期 JWT（建议 10–15 分钟），前端仅内存保存。
- Refresh Token：随机不透明 Token，使用 `HttpOnly; Secure; SameSite=Lax` Cookie，服务端只保存哈希。
- Refresh Token 每次使用都轮换；检测旧 Token 复用时撤销整个 Token Family。
- 所有请求由 Token 推导用户、租户和权限，忽略客户端伪造的租户头。

认证接口：

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/auth/login` | Public | 登录，受 IP/账号双维度限流 |
| POST | `/auth/refresh` | Refresh Cookie | 轮换会话 |
| POST | `/auth/logout` | Authenticated | 撤销当前会话 |
| POST | `/auth/logout-all` | Authenticated | 撤销用户所有会话 |
| GET | `/auth/me` | Authenticated | 当前用户、租户、角色、权限 |
| GET | `/auth/sessions` | Authenticated | 设备会话列表 |
| DELETE | `/auth/sessions/{session_id}` | Authenticated | 撤销指定会话 |
| POST | `/auth/password/forgot` | Public | 始终返回一致结果，防枚举 |
| POST | `/auth/password/reset` | Reset Token | 重置密码 |

SSO/OIDC、MFA 和 SCIM 预留在 `auth` 模块，首期可按客户优先级实现。

## 5.3 通用请求约定

### 请求头

| Header | 场景 | 说明 |
|---|---|---|
| `Authorization: Bearer <token>` | 用户 API | Access Token |
| `X-Request-ID` | 可选 | 客户端请求追踪；服务端会校验/生成 |
| `Idempotency-Key` | 创建报价、发送消息、触发工作流等 | 同租户、同路由范围内唯一 |
| `If-Match` | 更新高并发资源 | 使用资源版本，避免覆盖更新 |
| `Accept-Language` | 可选 | 错误消息本地化 |

### 列表分页

高增长列表使用游标：

```json
{
  "data": [],
  "meta": {
    "next_cursor": "opaque-token",
    "has_more": false
  }
}
```

后台小型字典可使用 `page/page_size`。默认 20，最大 100。允许的筛选和排序字段必须白名单化。

### 单资源响应

```json
{
  "data": {
    "id": "01J...",
    "created_at": "2026-07-23T16:00:00.000000Z",
    "updated_at": "2026-07-23T16:00:00.000000Z",
    "version": 3
  },
  "meta": {
    "request_id": "req_..."
  }
}
```

### 错误响应

```json
{
  "error": {
    "code": "QUOTATION_INVALID_TRANSITION",
    "message": "Quotation cannot be sent before approval.",
    "details": [
      {
        "field": "status",
        "reason": "approval_required"
      }
    ],
    "request_id": "req_..."
  }
}
```

错误码稳定、消息可本地化。生产错误不返回堆栈、SQL、上游密钥或原始响应。

## 5.4 HTTP 语义

| 状态码 | 用途 |
|---:|---|
| 200 | 查询/更新成功 |
| 201 | 创建成功 |
| 202 | 已接受异步任务 |
| 204 | 删除/无响应体操作成功 |
| 400 | 请求语义错误 |
| 401 | 未认证或令牌失效 |
| 403 | 无权限 |
| 404 | 资源不存在或不属于当前租户 |
| 409 | 幂等冲突、状态冲突、版本冲突 |
| 422 | 字段校验失败 |
| 429 | 限流/配额 |
| 502/503 | 上游或服务暂不可用 |

删除默认软删除。状态动作使用显式命令端点，例如 `/quotations/{id}/approve`，避免通过通用 PATCH 绕过状态机。

## 5.5 Dashboard

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/dashboard/summary` | `dashboard.read` | 客户、会话、报价、AI 概览 |
| GET | `/dashboard/inquiry-trend` | `dashboard.read` | 询盘趋势 |
| GET | `/dashboard/conversion-funnel` | `dashboard.read` | 意向/报价漏斗 |
| GET | `/dashboard/agent-performance` | `dashboard.read` | AI 响应、接管、成本 |

所有聚合接口要求时间范围、时区和最大跨度限制；大报表走异步导出。

## 5.6 Customer

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/customers` | `customer.read_*` | 按负责人、阶段、评分、标签、来源筛选 |
| POST | `/customers` | `customer.create` | 创建客户 |
| GET | `/customers/{customer_id}` | `customer.read_*` | 客户详情 |
| PATCH | `/customers/{customer_id}` | `customer.update_*` | 更新档案，使用版本控制 |
| DELETE | `/customers/{customer_id}` | `customer.delete` | 软删除/匿名化流程 |
| POST | `/customers/{customer_id}/assign` | `customer.assign` | 分配销售 |
| POST | `/customers/{customer_id}/tags` | `customer.update_*` | 添加标签 |
| DELETE | `/customers/{customer_id}/tags/{tag}` | `customer.update_*` | 移除标签 |
| GET | `/customers/{customer_id}/sessions` | `conversation.read_*` | 渠道会话 |
| GET | `/customers/{customer_id}/timeline` | `customer.read_*` | 统一时间线 |
| POST | `/customers/{customer_id}/recalculate-score` | `customer.score` | 异步重算意向 |

评分响应包含总分、等级、分项、解释、版本和计算时间，不只返回单个数字。

## 5.7 Conversation

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/conversations` | `conversation.read_*` | 会话队列 |
| GET | `/conversations/{conversation_id}` | `conversation.read_*` | 会话详情 |
| GET | `/conversations/{conversation_id}/messages` | `conversation.read_*` | 游标消息历史 |
| POST | `/conversations/{conversation_id}/messages` | `message.send` | 人工发送，要求幂等键 |
| POST | `/conversations/{conversation_id}/assign` | `conversation.assign` | 分配销售 |
| POST | `/conversations/{conversation_id}/takeover` | `conversation.takeover` | 切换人工模式 |
| POST | `/conversations/{conversation_id}/resume-ai` | `conversation.ai_manage` | 恢复 AI，需记录原因 |
| POST | `/conversations/{conversation_id}/close` | `conversation.close` | 关闭会话 |
| POST | `/conversations/{conversation_id}/reopen` | `conversation.reopen` | 重开会话 |
| POST | `/conversations/{conversation_id}/read` | `conversation.read_*` | 更新已读位置 |
| GET | `/conversations/{conversation_id}/ai-runs` | `ai_run.read` | AI 决策、引用、消耗 |

实时更新首选 SSE；需要双向在线状态时再采用 WebSocket。断线后客户端通过游标补拉，不能只依赖实时通道。

## 5.8 AI Agent 与 Prompt

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/ai-agent/preview` | `ai_agent.preview` | 使用脱敏测试上下文预览，不发送客户 |
| POST | `/ai-agent/evaluate` | `ai_agent.evaluate` | 运行离线测试集 |
| GET | `/ai-agent/runs` | `ai_run.read` | 运行列表与成本筛选 |
| GET | `/ai-agent/runs/{run_id}` | `ai_run.read` | 结构化输入输出、引用、策略结果 |
| POST | `/ai-agent/runs/{run_id}/feedback` | `ai_run.feedback` | 人工评价 |
| GET | `/prompts` | `prompt.read` | Prompt 列表 |
| POST | `/prompts` | `prompt.create` | 创建草稿 |
| GET | `/prompts/{prompt_id}` | `prompt.read` | 指定版本 |
| PATCH | `/prompts/{prompt_id}` | `prompt.update` | 仅草稿可修改 |
| POST | `/prompts/{prompt_id}/publish` | `prompt.publish` | 发布不可变版本 |
| POST | `/prompts/{prompt_id}/retire` | `prompt.publish` | 停用新流量 |

通用聊天接口不得让前端传任意 Dify App ID、API Key、系统 Prompt 或 Dataset ID。

## 5.9 RAG 知识库

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/knowledge/collections` | `knowledge.read` | 集合列表 |
| POST | `/knowledge/collections` | `knowledge.manage` | 创建并映射 Dataset |
| PATCH | `/knowledge/collections/{id}` | `knowledge.manage` | 更新元数据 |
| DELETE | `/knowledge/collections/{id}` | `knowledge.delete` | 受引用检查的异步删除 |
| POST | `/knowledge/files/upload-intents` | `knowledge.upload` | 获取预签名上传信息 |
| POST | `/knowledge/files` | `knowledge.upload` | 确认上传并创建处理任务 |
| GET | `/knowledge/files` | `knowledge.read` | 文件与同步状态 |
| GET | `/knowledge/files/{file_id}` | `knowledge.read` | 文件详情 |
| GET | `/knowledge/files/{file_id}/chunks` | `knowledge.read` | 分块预览 |
| POST | `/knowledge/files/{file_id}/resync` | `knowledge.manage` | 幂等重同步 |
| DELETE | `/knowledge/files/{file_id}` | `knowledge.delete` | 202 异步删除 |
| POST | `/knowledge/search-preview` | `knowledge.test` | 管理员检索测试 |

上传意图限制文件类型、大小和数量；对象 Key 由服务端生成，客户端不能指定任意存储路径。

## 5.10 Product 与 Quotation

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET/POST | `/products` | `product.read/create` | 产品列表/创建 |
| GET/PATCH/DELETE | `/products/{id}` | 对应权限 | 产品详情/更新/停用 |
| POST | `/quotations/assist` | `quotation.ai_assist` | AI 建议，返回草稿候选，不直接创建正式报价 |
| GET/POST | `/quotations` | `quotation.read_*/create` | 报价列表/创建 |
| GET/PATCH | `/quotations/{id}` | `quotation.read_*/update_*` | 详情/仅草稿更新 |
| POST | `/quotations/{id}/submit` | `quotation.submit` | 提交审批 |
| POST | `/quotations/{id}/approve` | `quotation.approve` | 审批，记录理由 |
| POST | `/quotations/{id}/reject` | `quotation.approve` | 驳回 |
| POST | `/quotations/{id}/send` | `quotation.send` | 异步发送，要求幂等键 |
| POST | `/quotations/{id}/cancel` | `quotation.cancel` | 取消 |
| GET | `/quotations/{id}/document` | `quotation.read_*` | 获取短期下载 URL |

服务端根据报价项重新计算所有金额并验证币种、折扣权限、最小起订量和有效期，忽略客户端提交的总额。

## 5.11 Connector

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/connectors/providers` | `connector.read` | 支持渠道与配置 Schema，不含密钥 |
| GET/POST | `/connectors` | `connector.read/manage` | 连接器列表/创建 |
| GET/PATCH/DELETE | `/connectors/{id}` | 对应权限 | 管理连接器 |
| PUT | `/connectors/{id}/config` | `connector.secret_manage` | 写入加密配置，响应只返回掩码 |
| POST | `/connectors/{id}/test` | `connector.manage` | 异步连接测试 |
| POST | `/connectors/{id}/activate` | `connector.manage` | 启用 |
| POST | `/connectors/{id}/deactivate` | `connector.manage` | 停用 |
| POST | `/connectors/{id}/rotate-secret` | `connector.secret_manage` | 轮换 webhook 密钥 |
| GET | `/connectors/{id}/webhook-logs` | `connector.log_read` | 脱敏日志 |
| POST | `/connectors/{id}/webhook-logs/{log_id}/replay` | `connector.replay` | 幂等重放 |

对外 webhook：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/hooks/v1/connectors/{connector_public_id}/events` | 兼容渠道验证和事件投递 |
| POST | `/hooks/v1/n8n/callbacks/{workflow_public_id}` | 若必须公网回调，使用独立签名与重放保护 |

Webhook 验证顺序：请求体大小限制 → 时间戳窗口 → 签名 → Connector 状态 → 幂等落库。响应不泄露租户、连接器或签名错误细节。

## 5.12 Workflow

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET/POST | `/workflows` | `workflow.read/manage` | 工作流列表/草稿 |
| GET/PATCH/DELETE | `/workflows/{id}` | 对应权限 | 管理草稿 |
| POST | `/workflows/{id}/validate` | `workflow.manage` | 校验节点、引用和 Secret |
| POST | `/workflows/{id}/publish` | `workflow.publish` | 发布并同步 n8n |
| POST | `/workflows/{id}/activate` | `workflow.publish` | 启用 |
| POST | `/workflows/{id}/deactivate` | `workflow.publish` | 停用 |
| POST | `/workflows/{id}/test` | `workflow.test` | 使用测试数据执行 |
| GET | `/workflows/{id}/runs` | `workflow.run_read` | 运行记录 |

n8n 内部 API 使用服务账户、HMAC/mTLS、时间戳和请求 ID；不复用普通用户 Token。

## 5.13 Notification

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/notifications` | Authenticated | 当前用户通知 |
| GET | `/notifications/unread-count` | Authenticated | 未读数 |
| POST | `/notifications/{id}/read` | Owner | 标记已读 |
| POST | `/notifications/read-all` | Authenticated | 全部已读 |
| GET/PATCH | `/notification-preferences` | Authenticated | 个人通知偏好 |
| POST | `/notifications/{id}/retry` | `notification.retry` | 管理员重试失败投递 |

## 5.14 System 与审计

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/system/users` | `user.read` | 用户列表 |
| POST | `/system/users/invitations` | `user.invite` | 邀请用户 |
| PATCH | `/system/users/{id}` | `user.manage` | 状态与资料 |
| GET/POST | `/system/roles` | `role.read/manage` | 角色管理 |
| GET | `/system/permissions` | `role.read` | 权限字典 |
| PUT | `/system/configs/{key}` | `system_config.manage` | 更新租户配置 |
| GET | `/system/configs` | `system_config.read` | Secret 仅返回配置状态 |
| GET | `/system/audit-logs` | `audit.read` | 只读审计检索 |
| POST | `/system/exports` | `data.export` | 异步导出并审计 |
| GET | `/system/jobs/{job_id}` | 资源对应权限 | 异步任务状态 |

## 5.15 事件契约

Outbox 事件信封：

```json
{
  "event_id": "01J...",
  "event_type": "conversation.message.received.v1",
  "occurred_at": "2026-07-23T16:00:00.000000Z",
  "tenant_id": "01J...",
  "aggregate": {
    "type": "conversation",
    "id": "01J...",
    "version": 12
  },
  "trace_id": "tr_...",
  "data": {}
}
```

事件名包含版本；消费者忽略未知可选字段。事件载荷默认只放 ID 和必要快照，消费者按权限通过内部 API 获取敏感数据。

建议首期事件：

- `conversation.message.received.v1`
- `conversation.ai_reply.requested.v1`
- `conversation.handoff.requested.v1`
- `customer.intent.changed.v1`
- `quotation.approval.requested.v1`
- `quotation.sent.v1`
- `knowledge.file.sync.requested.v1`
- `connector.delivery.failed.v1`
- `notification.requested.v1`

## 5.16 限流与配额

限流维度包括 IP、用户、租户、连接器、会话和 Dify App。建议策略：

- 登录：严格滑动窗口并配合失败锁定。
- webhook：按 Connector 独立桶，允许合理突发。
- 发送消息/AI 预览：按用户与租户双层限制。
- 文件上传/导出：限制并发、单文件大小、日总量。
- 超配额返回 `429`，包含安全的 `Retry-After`；不得因单一大租户耗尽全局 Worker。

## 5.17 API 兼容与验收

- `/api/v1` 内仅做向后兼容增加；破坏性变更进入 `/api/v2`。
- OpenAPI 是 HTTP 契约事实来源；Connector webhook 另存原始载荷样例和签名测试向量。
- 契约测试覆盖前端客户端、Dify/n8n Adapter 和各 Connector。
- 上线前必须通过：租户越权测试、RBAC 测试、幂等重放、并发状态流转、Secret 泄漏扫描、文件上传安全、Dify 超时降级和数据库恢复演练。

