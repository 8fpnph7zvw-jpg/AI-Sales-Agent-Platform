# 企业级 Demo 初始化

`backend/scripts/initialize_demo.py` 使用 SQLAlchemy Async ORM 在一个事务中初始化
Demo 数据，不包含手写 SQL。脚本以租户、业务稳定键和表唯一键查询后更新或创建，
因此可以重复执行而不会产生重复数据。

## 初始化内容

- 租户：`AI Sales Demo`（slug：`demo`）
- 管理员：`admin@test.com`
- 客户：ABC Electronics、Amazon Buyer Test、European Importer
- Connector：WhatsApp、Alibaba、Amazon、Feishu；全部为 `disabled`
- Workflow：客户询盘 → AI 自动回复 → 意向评分 → 高意向通知销售
- 知识库：产品FAQ；包含产品介绍、价格规则、运输方式、售后政策
- 产品：Wireless Earphone、Smart Watch、USB Charger
- 报价模板：`DEMO-TEMPLATE-001` 草稿报价

Connector 仅是无凭证模板，不会连接或调用真实渠道 API。

## Docker 部署

首次部署前，在 `.env` 中修改 Demo 管理员初始密码：

```dotenv
DEMO_ADMIN_PASSWORD=replace-with-a-strong-demo-password
```

构建并启动：

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 migration
```

`migration` 服务会先执行 Alembic，再自动运行 Demo 初始化。日志中出现
`Enterprise demo initialized` 表示初始化成功。

任何时候都可以安全地重复运行：

```bash
docker compose run --rm migration
```

已有 `admin@test.com` 的密码不会被脚本重置；`DEMO_ADMIN_PASSWORD` 只在首次创建
该管理员时生效。

## 验收

登录参数：

- tenant slug：`demo`
- email：`admin@test.com`
- password：`.env` 中的 `DEMO_ADMIN_PASSWORD`

登录后检查客户、Connector、Workflow、知识库和报价管理页面。Agent 页面应只要求
选择客户和输入问题；首次提交时后端自动创建 conversation。

也可以直接检查初始化日志和 API：

```bash
curl http://127.0.0.1/healthz
curl -s http://127.0.0.1/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"tenant_slug":"demo","email":"admin@test.com","password":"YOUR_PASSWORD"}'
```

取得 `access_token` 后，使用 Bearer Token 请求：

```text
GET /api/v1/customers
GET /api/v1/connectors
GET /api/v1/workflows
GET /api/v1/knowledge/files
GET /api/v1/products
GET /api/v1/quotations
POST /api/v1/conversations
```
