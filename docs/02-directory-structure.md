# 2. 目标目录结构

以下是确认架构后创建的目标结构。本阶段不生成其中的业务实现文件。

```text
ai-sales-agent-platform/
├─ frontend/                         # Vue 3 + TypeScript + Element Plus
│  ├─ public/
│  ├─ src/
│  │  ├─ api/                        # 按领域封装同源 /api/v1 请求
│  │  ├─ assets/
│  │  ├─ components/
│  │  │  ├─ business/
│  │  │  └─ common/
│  │  ├─ composables/
│  │  ├─ directives/
│  │  ├─ layouts/
│  │  ├─ locales/
│  │  ├─ router/
│  │  ├─ stores/                     # Pinia；会话、权限、租户上下文
│  │  ├─ styles/
│  │  ├─ types/
│  │  ├─ utils/
│  │  ├─ views/
│  │  │  ├─ auth/
│  │  │  ├─ dashboard/
│  │  │  ├─ customers/
│  │  │  ├─ conversations/
│  │  │  ├─ knowledge/
│  │  │  ├─ quotations/
│  │  │  ├─ connectors/
│  │  │  ├─ workflows/
│  │  │  ├─ notifications/
│  │  │  └─ system/
│  │  ├─ App.vue
│  │  └─ main.ts
│  ├─ tests/
│  │  ├─ unit/
│  │  └─ e2e/
│  ├─ .env.example                   # 仅公开构建变量，不含服务端密钥
│  ├─ Dockerfile
│  ├─ package.json
│  ├─ tsconfig.json
│  └─ vite.config.ts
│
├─ backend/                          # FastAPI + SQLAlchemy
│  ├─ app/
│  │  ├─ api/
│  │  │  ├─ dependencies/            # 当前用户、权限、分页、幂等键
│  │  │  ├─ errors/
│  │  │  ├─ middleware/
│  │  │  └─ v1/                      # 路由聚合，不写领域规则
│  │  ├─ modules/
│  │  │  ├─ auth/
│  │  │  ├─ customer/
│  │  │  ├─ conversation/
│  │  │  ├─ ai_agent/
│  │  │  ├─ rag/
│  │  │  ├─ quotation/
│  │  │  ├─ connector/
│  │  │  ├─ workflow/
│  │  │  ├─ notification/
│  │  │  └─ system/
│  │  │     # 每个模块按需包含 router/service/repository/
│  │  │     # model/schema/domain/events/policies
│  │  ├─ integrations/
│  │  │  ├─ dify/
│  │  │  ├─ n8n/
│  │  │  ├─ object_storage/
│  │  │  └─ connectors/              # 各渠道 Adapter
│  │  ├─ core/                       # 配置、日志、安全、异常、常量
│  │  ├─ db/                         # Session、Base、UoW、租户过滤
│  │  ├─ cache/
│  │  ├─ jobs/                       # Worker、Scheduler、Outbox 消费
│  │  ├─ observability/
│  │  └─ main.py
│  ├─ alembic/
│  │  └─ versions/
│  ├─ scripts/                       # 运维/初始化脚本，不放业务逻辑
│  ├─ tests/
│  │  ├─ unit/
│  │  ├─ integration/
│  │  ├─ contract/
│  │  └─ factories/
│  ├─ .env.example
│  ├─ alembic.ini
│  ├─ Dockerfile
│  └─ pyproject.toml
│
├─ database/
│  ├─ migrations/                    # 设计归档；实际执行以 Alembic 为准
│  ├─ seeds/                         # 权限/系统字典等幂等种子
│  ├─ init/                          # 仅数据库级初始化
│  ├─ backup/
│  └─ README.md
│
├─ docker/
│  ├─ compose/
│  │  ├─ compose.base.yml
│  │  ├─ compose.dev.yml
│  │  └─ compose.prod.yml
│  ├─ mysql/
│  ├─ redis/
│  ├─ n8n/
│  └─ scripts/
│
├─ nginx/
│  ├─ conf.d/
│  │  ├─ default.conf
│  │  ├─ proxy.conf
│  │  └─ security.conf
│  ├─ snippets/
│  ├─ certs/                          # 本地挂载目录；证书不入库
│  └─ Dockerfile
│
├─ docs/
│  ├─ 01-architecture.md
│  ├─ 02-directory-structure.md
│  ├─ 03-deployment.md
│  ├─ 04-database-er.md
│  ├─ 05-api-design.md
│  ├─ adr/                            # Architecture Decision Records
│  ├─ api/                            # OpenAPI 与 webhook 契约
│  ├─ runbooks/                       # 故障、恢复、轮换、备份手册
│  └─ README.md
│
├─ tests/
│  ├─ e2e/
│  └─ performance/
├─ .env.example                      # Compose 变量模板，无真实值
├─ .gitignore
├─ compose.yml                       # 默认组合入口
├─ Makefile                          # 可选的跨平台命令入口
└─ README.md
```

## 2.1 后端模块内部约定

典型模块按职责拆分，而不是要求每个模块机械复制所有文件：

```text
modules/<module>/
├─ router.py          # HTTP 协议、状态码、依赖注入
├─ schemas.py         # 输入/输出 DTO
├─ service.py         # 应用用例与事务编排
├─ domain.py          # 领域规则与值对象
├─ policies.py        # 权限与业务策略
├─ repository.py      # 持久化接口/查询
├─ models.py          # SQLAlchemy 映射
├─ events.py          # 领域/Outbox 事件
└─ exceptions.py
```

依赖方向为 `router -> service -> domain/repository interface`，第三方 SDK 只能出现在 `integrations` 或对应 Adapter。模块之间通过明确的服务接口或事件协作，禁止跨模块随意操作对方数据表。

## 2.2 前端约定

- 路由和按钮权限均由后端权限集合驱动，但后端必须再次授权，前端隐藏按钮不是安全控制。
- API 层统一处理错误码、刷新令牌、请求 ID、取消请求和下载。
- Pinia 不持久化敏感令牌；本地存储只保存无敏感性的 UI 偏好。
- 页面按领域分包和懒加载；通用组件不包含业务数据请求。

## 2.3 环境文件边界

- 根 `.env`：Compose 运行变量，由部署人员维护。
- `backend/.env.example`：后端变量说明，仅示例占位符。
- `frontend/.env.example`：只能出现可公开变量，例如 `VITE_APP_TITLE`、`VITE_API_BASE=/api/v1`。
- 任何 `VITE_*` 都会进入浏览器产物，因此绝不能放 API Key、密码或连接器密钥。

