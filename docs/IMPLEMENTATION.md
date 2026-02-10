# 软件质量管理平台 P0 实施说明

## 目标
- 以版本为主线，打通测试用例、问题单、看板与配置中心闭环。
- Phase 1：前端原型壳（Mock）
- Phase 2：FastAPI + PostgreSQL 实际 API

## 当前实现状态
- `frontend/`：React + TS + Ant Design，已实现 `/login`、`/`、`/cases`、`/issues`、`/settings`。
- `backend/`：FastAPI 接口、SQLAlchemy 模型、Alembic 初始迁移、JWT 登录、RBAC、附件上传、CSV/XLSX 导入导出。
- `deploy/`：docker-compose + Nginx 反向代理 + uploads 静态目录映射。

## 默认账户
- `admin / password123`
- `qa / password123`
- `dev / password123`
- `viewer / password123`

## 运行方式
1. 前端：`make frontend-dev`
2. 后端：`make backend-install && make backend-run`
3. 容器：`make docker-up`
4. 默认访问：`http://localhost:8080`

## 中国大陆部署镜像源
- npm 源：`/Users/liangchenzhang/PycharmProjects/Release-Quality-Management-Platform/frontend/.npmrc`（`registry.npmmirror.com`）。
- pip 源：`/Users/liangchenzhang/PycharmProjects/Release-Quality-Management-Platform/backend/pip.conf`（清华 PyPI 源）。
- Docker 拉取：`docker.1ms.run`（已用于 Dockerfile 与 compose 的基础镜像）。
- Docker daemon 镜像加速：`/Users/liangchenzhang/PycharmProjects/Release-Quality-Management-Platform/deploy/docker/daemon.1ms.json`。
- Nginx 端口映射：`${HOST_HTTP_PORT:-8080}:80`，可通过 `HOST_HTTP_PORT=80 make docker-up` 覆盖。

## 前端数据源切换
- Mock（默认）：`VITE_DATA_SOURCE=mock`
- 真实 API：`VITE_DATA_SOURCE=api` 且 `VITE_API_BASE_URL=/api/v1`
- 参考：`/Users/liangchenzhang/PycharmProjects/Release-Quality-Management-Platform/frontend/.env.example`

## 关键约束
- 单项目单实例。
- 顶部版本切换只影响个人视图（前端 localStorage 键：`qms.viewVersionKey`）。
- 问题单内部细粒度状态，前端按 `all/open/pending/closed/invalid` 状态组展示。
