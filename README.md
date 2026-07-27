# AI Sales Agent Platform

面向跨境企业的云端 AI Sales Agent 平台，当前已完成总体架构、MySQL 数据库基线、
FastAPI 核心业务层和 Docker Compose 云端部署配置。

## 当前数据库实现

- MySQL 8.0 / `utf8mb4`
- SQLAlchemy 2.x Async ORM（应用使用 `asyncmy`）
- Alembic（迁移使用 `PyMySQL`）
- 30 张企业级多租户数据表，包含 RAG 文档、切片和 Embedding 持久化
- RBAC、客户、聊天、Dify AI 运行、RAG、Connector、Workflow、报价、通知、审计和 Outbox
- Router → Service → Repository 分层 REST API
- RAG V3：PDF/Word/Excel 解析、文本切片、本地 Embedding、Chroma 同步和租户隔离检索

入口文档：

- `docs/README.md`
- `docs/04-database-er.md`
- `docs/06-database-implementation.md`
- `docs/07-backend-business-api.md`
- `docs/08-cloud-docker-deployment.md`
- `database/README.md`

本仓库仍处于分阶段建设中，前端管理台、Worker 和具体渠道 Adapter 尚未完整生成。

## OpenWA WhatsApp 微服务

OpenWA 以 Git submodule 和独立 Docker 服务接入 `services/openwa`。启动、Session
配对、自动 API Key 初始化和 Webhook 注册见
`docs/10-whatsapp-business-connector.md`。
