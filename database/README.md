# Database

数据库目标版本为 MySQL 8.0，字符集为 `utf8mb4`，所有时间按 UTC 保存。

## 文件

- `init/001_schema.sql`：完整基线 DDL，适合创建全新数据库或数据库容器首次初始化。
- `init/002_permissions_seed.sql`：幂等的全局权限字典。
- `../backend/alembic/`：生产发布的版本化迁移入口。

## 使用原则

全新本地数据库可以顺序执行 `001_schema.sql` 和 `002_permissions_seed.sql`。已经运行的平台不得重新执行基线文件，也不得手工修改表结构；所有结构变更通过新的 Alembic revision 发布。

生产发布以 `alembic upgrade head` 为准。SQL 初始化文件用于空库初始化、审查和灾难恢复，不替代版本化迁移。

