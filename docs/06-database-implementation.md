# 6. 数据库实现与迁移方案

## 6.1 已实现范围

MySQL 8.0 基线包含 28 张表，覆盖：

- 租户、用户、角色、权限、登录会话
- 客户、渠道身份、销售归属与意向评分
- 业务会话、消息和 Dify Agent 运行
- Prompt、知识集合、文件与分块
- Connector、加密配置和 webhook 日志
- Workflow 与节点
- 产品、报价与报价明细
- 通知、系统配置、审计日志与 Outbox

SQLAlchemy 模型按领域目录组织，每个模型独立文件。模型聚合入口为 `backend/app/models/__init__.py`，Alembic 通过该入口获得完整 Metadata。

## 6.2 基线文件

| 文件 | 用途 |
|---|---|
| `database/init/001_schema.sql` | 空库的 28 张表、约束和索引 |
| `database/init/002_permissions_seed.sql` | 幂等的全局权限字典 |
| `backend/alembic/versions/20260724_0001_initial_schema.py` | Alembic 首次迁移 |
| `backend/alembic/env.py` | Metadata、连接 URL 和迁移上下文 |
| `backend/alembic.ini` | Alembic 配置 |

Compose 创建全新 MySQL 数据卷时会自动按文件名顺序执行 `database/init`。生产发布统一执行 Alembic，不重复执行初始化脚本。

## 6.3 驱动与连接

- FastAPI/Worker：`mysql+asyncmy`
- Alembic：将同一 URL 转为同步 `mysql+pymysql`
- 字符集：`utf8mb4`
- 排序规则：`utf8mb4_0900_ai_ci`
- 时区：连接与容器使用 UTC

示例：

```text
DATABASE_URL=mysql+asyncmy://<user>:<password>@mysql:3306/ai_sales_agent?charset=utf8mb4
```

密码只通过环境变量或 Secret 注入，不写入 `alembic.ini` 的真实配置。

## 6.4 迁移命令

在 `backend/` 目录执行：

```bash
alembic current
alembic upgrade head
alembic downgrade -1
alembic revision --autogenerate -m "add customer segment"
alembic check
```

离线审查 SQL：

```bash
alembic upgrade head --sql
```

首个 revision 会执行已冻结的两份基线 SQL。基线一旦部署就不得修改；后续 revision 必须使用显式 `op.create_table`、`op.add_column`、`op.create_index` 等操作。

## 6.5 发布流程

1. 对目标库执行备份并验证恢复点。
2. 检查当前 revision 与应用版本是否匹配。
3. 在 CI 中执行模型导入、Mapper 配置、MySQL 方言编译、单元测试和 `alembic check`。
4. 运行一次性 migration 容器执行 `alembic upgrade head`。
5. 迁移成功后再启动新 API/Worker。
6. 执行读写烟雾测试，监控锁等待、慢查询和错误率。
7. 数据回填通过独立、可恢复、可观察的批处理完成。

MySQL DDL 通常会隐式提交，不能假设整个 revision 可事务回滚。迁移脚本必须小而可恢复，生产执行前需要在同版本副本验证。

## 6.6 Expand / Migrate / Contract

破坏性变更分三个版本发布：

1. **Expand**：增加可空列、新表或新索引；旧代码仍可运行。
2. **Migrate**：部署双写/兼容读取并分批回填，验证数据完整性。
3. **Contract**：所有实例切换后，后续 revision 再删除旧列、旧索引或兼容逻辑。

禁止在同一次部署中直接重命名高流量列、把大表字段改为非空并全表回填，或删除仍被旧实例使用的结构。

## 6.7 索引与锁风险

- 业务索引以 `tenant_id` 开头，再组合状态、负责人和排序时间。
- 新增大表索引前使用生产等量副本测量耗时和临时空间。
- MySQL 版本支持时显式评估 `ALGORITHM=INSTANT/INPLACE` 和 `LOCK=NONE`，不盲目依赖默认值。
- `messages`、`webhook_logs`、`audit_logs`、`outbox_events` 是主要增长表，需要保留策略、归档和容量告警。

## 6.8 回滚策略

- 应用回滚与数据库回滚分开决策；优先保持向后兼容并回滚应用。
- 纯增加型 revision 通常无需立即 downgrade。
- 会丢数据的 downgrade 不自动执行，改用前向修复 revision。
- 基线 downgrade 仅用于空的开发/测试环境，会删除全部 28 张表。

## 6.9 旧草稿兼容说明

本工作区原有 Connector Hub 草稿使用 UUID、`connector_instances`、SQLite/PostgreSQL 驱动，且没有正式 Alembic 历史。本次基线按新平台重新建模，不提供旧草稿数据的自动迁移。

如果旧库已经存在业务数据，必须单独编写一次性 ETL：旧 ID 映射到新 `BIGINT + public_id`、连接器实例映射到 `connectors`、旧消息补齐客户/会话关系，并在切换前完成数量、哈希和抽样核对。

## 6.10 验证覆盖

自动化检查包括：

- 28 个 SQL 表与 28 个 ORM 表名称一致
- 每张表的 SQL 列与 ORM 列一致
- 全部 Mapper 和 Relationship 可配置
- 所有表可由 SQLAlchemy MySQL 方言编译
- 外键整数使用 `BIGINT UNSIGNED`
- MySQL 标识符不超过 64 字符
- Alembic 只有一个线性 Head
- 基线 SQL 可被 Alembic 离线升级完整展开
