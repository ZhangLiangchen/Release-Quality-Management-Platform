# 导入模板说明

## 用例导入（`/api/v1/cases:import`）
必填列：
- `case_key`
- `title`
- `module`
- `steps`
- `expected`

可选列：
- `tags`（逗号分隔）

参数：
- `mode=upsert|add_only`
- `validate_only=true|false`

## 问题单导入（`/api/v1/issues:import`）
必填列：
- `issue_key`
- `title`
- `found_version_key`

可选列：
- `description`
- `status`（仅开放态）
- `priority`
- `severity`

参数：
- `mode=upsert|add_only`
- `validate_only=true|false`

支持文件：`.csv`、`.xlsx`
