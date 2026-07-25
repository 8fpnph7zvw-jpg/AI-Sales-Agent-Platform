# Docker 部署文件

部署入口位于项目根目录的 `docker-compose.yml`。

- `backend/Dockerfile`：FastAPI 与 Alembic 共用的非 root 运行镜像
- `frontend/Dockerfile`：Vue3 多阶段构建及静态 Nginx 镜像
- `frontend/docker/nginx.conf`：SPA 静态资源配置
- `nginx/nginx.conf`：公网入口和 `/api/v1` 反向代理
- `.env.example`：无真实凭据的环境变量契约
- `docs/08-cloud-docker-deployment.md`：部署、升级、备份和故障排查
