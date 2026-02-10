# Release-Quality-Management-Platform

软件质量管理平台（P0）

## 技术栈
- Frontend: React + TypeScript + Vite + Ant Design
- Backend: FastAPI + SQLAlchemy + Alembic + PostgreSQL
- Gateway: Nginx
- Deployment: Docker Compose

## 功能页面
- `/` 首页看板
- `/cases` 测试用例集
- `/issues` 问题单
- `/cicd` CICD（Hyperchain 二进制占位流程）
- `/perf-automation` 性能测试自动化（frigateDynamic）
- `/func-automation` 功能测试自动化（hypersonic）
- `/settings` 配置中心

## 目录结构
- `frontend/`: 前端应用（Phase 1 可用 Mock 数据）
- `backend/`: 后端 API 与数据库迁移
- `deploy/`: `docker-compose` 与 Nginx 配置
- `docs/`: 实施说明与接口文档

## 快速开始
1. 安装前端依赖：`make frontend-install`
2. 安装后端依赖：`make backend-install`
3. 启动前端开发：`make frontend-dev`
4. 启动后端开发：`make backend-run`
5. 一键容器启动：`make docker-up`
6. 容器启动后默认访问：`http://localhost:8080`

## 前端数据源
- 默认使用 Mock：`VITE_DATA_SOURCE=mock`
- 切换真实后端：`VITE_DATA_SOURCE=api`，并设置 `VITE_API_BASE_URL=/api/v1`
- 示例配置见 `frontend/.env.example`

## 中国大陆镜像源
- `npm`：项目内固定为 `https://registry.npmmirror.com/`（见 `/Users/liangchenzhang/PycharmProjects/Release-Quality-Management-Platform/frontend/.npmrc`）。
- `pip`：项目内固定为清华源 `https://pypi.tuna.tsinghua.edu.cn/simple`（见 `/Users/liangchenzhang/PycharmProjects/Release-Quality-Management-Platform/backend/pip.conf`）。
- Docker 基础镜像：使用 `docker.1ms.run` 前缀（见 `/Users/liangchenzhang/PycharmProjects/Release-Quality-Management-Platform/frontend/Dockerfile`、`/Users/liangchenzhang/PycharmProjects/Release-Quality-Management-Platform/backend/Dockerfile`、`/Users/liangchenzhang/PycharmProjects/Release-Quality-Management-Platform/deploy/docker-compose.yml`）。
- Docker daemon 1ms 镜像加速：参考 `/Users/liangchenzhang/PycharmProjects/Release-Quality-Management-Platform/deploy/docker/daemon.1ms.json`，Linux 可执行 `/Users/liangchenzhang/PycharmProjects/Release-Quality-Management-Platform/deploy/docker/setup-1ms-mirror.sh`。
- 宿主机端口可配置：默认 `8080`，可用 `HOST_HTTP_PORT=80 make docker-up` 覆盖（前提是 80 未被占用）。

## 默认测试账号
- admin / password123
- qa / password123
- dev / password123
- viewer / password123
