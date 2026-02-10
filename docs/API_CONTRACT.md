# API Contract (P0)

统一前缀：`/api/v1`
统一成功返回：`{ "data": ..., "trace_id": "..." }`
统一失败返回：`{ "error": { "code": "...", "message": "...", "details": {} }, "trace_id": "..." }`

## 认证
- `POST /auth/login`
- `GET /auth/me`

## 配置
- `GET /config`
- `PUT /config`

## 用户
- `GET /users`
- `POST /users`
- `DELETE /users/{user_id}`

## 版本
- `GET /versions`
- `POST /versions`
- `POST /versions/{version_key}:set-current`
- `DELETE /versions/{version_key}`

## 用例
- `GET /cases?version_key=...&group_by=module`
- `GET /cases/{case_key}?version_key=...`
- `PUT /versions/{version_key}/cases/{case_key}/status`
- `GET /versions/{version_key}/cases/{case_key}/history`
- `POST /cases:import`
- `GET /cases:export?version_key=...&format=xlsx`

## 问题单
- `GET /issues?version_key=...&status_group=...`
- `POST /issues`
- `PUT /issues/{issue_key}`
- `POST /issues/{issue_key}:transition`
- `POST /issues/{issue_key}:close`
- `POST /issues:import`
- `GET /issues:export?version_key=...&format=xlsx`

## 看板
- `GET /dashboard/quality?version_key=...`
- `GET /dashboard/issues/pending?version_key=...`

## 附件
- `POST /files/upload` (multipart/form-data)

## 健康检查
- `GET /healthz`
- `GET /readyz`
