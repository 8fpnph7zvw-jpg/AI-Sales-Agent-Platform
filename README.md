# AI Sales Agent Platform

面向企业的 AI Sales Agent 平台，包含 FastAPI 后端、Vue 管理后台、MySQL、
Redis、Dify Agent 集成和基于 Chroma 的 RAG 知识库。

## 核心架构

- FastAPI Router → Service → Repository 分层业务架构
- MySQL 8.4 与 SQLAlchemy 2.x Async ORM
- Redis 持久化服务
- Dify AI Agent 对话链路
- Chroma RAG 文档解析、切片和向量检索
- 统一 Connector 与 provider adapter 设计
- Vue 3 管理后台和 Nginx 入口
- Docker Compose 云端部署

## 文档

- `docs/README.md`
- `docs/04-database-er.md`
- `docs/06-database-implementation.md`
- `docs/07-backend-business-api.md`
- `docs/08-cloud-docker-deployment.md`
- `docs/10-whatsapp-business-connector.md`
- `database/README.md`

## WhatsApp Business

WhatsApp 保留统一 Connector 管理入口，FastAPI 通过 provider-neutral adapter
工作。当前内置 WhatsApp Cloud API adapter，后续可以在不修改 AI Agent 核心
业务的前提下增加其他 provider。
