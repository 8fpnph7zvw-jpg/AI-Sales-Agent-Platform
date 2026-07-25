# AI Sales Agent Platform — 架构设计包

状态：`持续建设中`

本目录包含架构、数据库、FastAPI 业务层和云端部署文档，不包含真实密钥。

## 文档清单

1. [总体架构](./01-architecture.md)
2. [目标目录结构](./02-directory-structure.md)
3. [Docker 部署方案](./03-deployment.md)
4. [MySQL ER 设计](./04-database-er.md)
5. [API 设计](./05-api-design.md)
6. [数据库实现与迁移方案](./06-database-implementation.md)
7. [FastAPI 业务层实现](./07-backend-business-api.md)
8. [云端 Docker Compose 部署](./08-cloud-docker-deployment.md)

## 本阶段关键结论

- 采用前后端完全分离的单域名部署：浏览器只访问 Nginx，`/` 提供前端静态资源，`/api/v1` 反向代理到内网 FastAPI。
- FastAPI、MySQL、Redis、n8n、对象存储均不映射公网端口；Dify API Key、渠道密钥和加密主密钥只存在于服务端。
- 平台按 SaaS 多租户设计，所有业务数据按 `tenant_id` 隔离，并使用 RBAC、审计日志和资源级授权形成纵深防护。
- 客户消息先持久化再异步处理，采用幂等、Inbox/Outbox、重试和死信机制，避免第三方平台重复推送或短暂故障造成数据丢失。
- Dify 负责 Agent 推理与向量检索；MySQL 保存知识文件、分块元数据、同步状态和 Dify 资源映射，不在 MySQL 中承担向量数据库职责。
- n8n 负责可编排自动化和外部通知，不承载登录鉴权、核心事务或客户消息的唯一事实来源。

## 请确认的架构决策

若无调整，第二阶段将按以下默认项实施：

1. 产品形态采用多租户 SaaS，而不是每家客户独立代码分支。
2. Dify 先作为外部 Agent API 接入；平台保存租户到 Dify App/Dataset 的映射。
3. 本地/私有化 Compose 使用 MinIO，云生产可切换到兼容 S3 的对象存储。
4. 首期认证采用邮箱密码 + RBAC，并预留 OIDC/SSO 与 MFA。
5. FastAPI 和 n8n 不开放独立公网管理地址；渠道只访问受保护的 webhook 路径。
6. 首批要真正实现的渠道 Adapter 需在编码前确定，其余渠道先遵循统一 Connector 契约。

## 评审后再进入的阶段

确认本设计后，第二阶段才会：

1. 清理或迁移当前工作区中与本方案冲突的 Connector Hub 草稿。
2. 创建目标目录与基础工程。
3. 生成 MySQL Alembic 迁移、后端模块骨架、前端管理台骨架。
4. 实现 Docker Compose、Nginx、健康检查和最小可运行链路。
