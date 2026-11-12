---
name: relay-workspace
description: Uses the Relay workspace API to query and modify the dedicated PostgreSQL database or manage files in the dedicated server directory. Use when asked to work with Relay workspace SQL, DDL, tables, or workspace files.
---

# Relay 开发工作区

从环境读取 `RELAY_WORKSPACE_URL` 和 `RELAY_WORKSPACE_TOKEN`。工作区使用单独的 Bearer 凭据，日志和回答只显示必要的执行结果。

- SQL 调用 `POST /v1/workspace/sql`。执行目标是开发库 `relay_developer`，使用 `public` schema。用 `%s` 和 `params` 绑定外部输入。
- 文件调用 `/v1/workspace/files`。路径是相对于工作目录的 URL 编码路径。用 GET 列出或下载，POST 建目录，PUT 上传或覆盖文件，DELETE 删除文件或空目录。
- 执行写入、删除和 DDL 前核对用户要求的对象与操作。SQL 请求独立提交事务，回报实际的命令结果和行数。

完整请求与响应说明见 [工作区 API](references/api.md)。
