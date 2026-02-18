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

## frigateDynamic Streamlit 真实集成页面验证
以服务器 `10.10.131.192` 为例，目标是查看 `/perf-automation` 页面中的真实 Streamlit 嵌入与调用日志。

1. 确认 Streamlit 服务在线（期望返回 `HTTP/1.1 200`）：
```bash
curl -I http://10.10.131.192:8501
```

2. 配置前端使用真实后端 API（非 mock）：
```bash
cat > /home/hyperchain/Release-Quality-Management-Platform/frontend/.env.production <<'EOF'
VITE_DATA_SOURCE=api
VITE_API_BASE_URL=/api/v1
EOF
```

3. 重新构建并启动相关容器（无需先手动 remove）：
```bash
cd /home/hyperchain/Release-Quality-Management-Platform
docker compose -f deploy/docker-compose.yml up -d --build --force-recreate backend frontend nginx
```

4. 打开页面验证：
- 地址：`http://10.10.131.192:8080/perf-automation`
- 触发“执行测试”后，执行日志中应出现 `streamlit_probe` 连通结果（例如：`[streamlit_probe] 已连通 http://10.10.131.192:8501 (HTTP 200)`）。

### 是否需要 remove 容器
- 一般不需要。执行上面的 `up -d --build --force-recreate ...` 即可完成重建和替换。

### 是否需要 `--no-cache`
- 一般不需要。
- 仅在“确认代码已更新但容器行为仍旧旧版本”时使用：
```bash
docker compose -f deploy/docker-compose.yml build --no-cache backend frontend
docker compose -f deploy/docker-compose.yml up -d backend frontend nginx
```

### 注意事项
- 不要执行 `docker compose down -v`，否则会删除数据库卷数据。

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

## 测试用例树与存量导入
新增了可编辑的用例树（目录/文件/用例）和文本用例导入脚本。部署后可按以下流程初始化：

1. 生成文本用例 JSON（本地执行）：
```bash
cd /Users/zhangliangchen/PycharmProjects/Release-Quality-Management-Platform
python3 backend/scripts/build_hypersonic_text_cases.py
```

2. 同步代码并重建容器（服务器执行）：
```bash
cd /home/hyperchain/Release-Quality-Management-Platform
docker compose -f deploy/docker-compose.yml up -d --build backend frontend nginx
```

3. 执行数据库迁移（服务器执行）：
```bash
docker compose -f deploy/docker-compose.yml exec backend alembic upgrade head
```

4. 导入存量用例并清理占位数据（服务器执行）：
```bash
docker compose -f deploy/docker-compose.yml exec backend python3 scripts/bootstrap_case_library.py
```
