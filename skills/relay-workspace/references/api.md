# Relay 工作区 API

配置 `RELAY_WORKSPACE_URL` 为部署方提供的 API 地址，固定 IP 部署的 HTTP 端口为 19016。把独立数据凭据设为 `RELAY_WORKSPACE_TOKEN`。所有请求都带上 `Authorization: Bearer $RELAY_WORKSPACE_TOKEN`。凭据在撤销前有效，HTTP 请求的凭据与内容为明文传输。

## PostgreSQL

`POST /v1/workspace/sql` 接收 `sql` 和可选 `params`。支持开发库内表、视图、索引等对象的 DDL，以及 INSERT、SELECT、UPDATE、DELETE。SQL 会在独立事务里执行，成功后提交。每次响应包含最后一个命令的 `command`、`row_count`、`columns`、`rows`、`truncated`。最多返回 1,000 行和 1 MiB。带参数的 SQL 用 `%s` 占位。

```sh
curl -fsS "$RELAY_WORKSPACE_URL/v1/workspace/sql" \
  -H "Authorization: Bearer $RELAY_WORKSPACE_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"sql":"CREATE TABLE IF NOT EXISTS demo_notes (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, body text NOT NULL)"}'

curl -fsS "$RELAY_WORKSPACE_URL/v1/workspace/sql" \
  -H "Authorization: Bearer $RELAY_WORKSPACE_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"sql":"INSERT INTO demo_notes(body) VALUES (%s) RETURNING id","params":["Relay 联调"]}'

curl -fsS "$RELAY_WORKSPACE_URL/v1/workspace/sql" \
  -H "Authorization: Bearer $RELAY_WORKSPACE_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"sql":"SELECT id, body FROM demo_notes ORDER BY id LIMIT 20"}'
```

## 文件

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/v1/workspace/files` | 列出根目录 |
| GET | `/v1/workspace/files/{path}` | 列出子目录或下载文件 |
| POST | `/v1/workspace/files/{path}` | 新建目录，上级目录需已存在 |
| PUT | `/v1/workspace/files/{path}` | 上传或覆盖文件，使用 `application/octet-stream`，每个文件最多 16 MiB |
| DELETE | `/v1/workspace/files/{path}` | 删除文件或空目录 |

```sh
curl -fsS -X POST "$RELAY_WORKSPACE_URL/v1/workspace/files/demo" \
  -H "Authorization: Bearer $RELAY_WORKSPACE_TOKEN"

curl -fsS -X PUT "$RELAY_WORKSPACE_URL/v1/workspace/files/demo/notes.txt" \
  -H "Authorization: Bearer $RELAY_WORKSPACE_TOKEN" \
  -H 'Content-Type: application/octet-stream' --data-binary @notes.txt

curl -fsS "$RELAY_WORKSPACE_URL/v1/workspace/files/demo/notes.txt" \
  -H "Authorization: Bearer $RELAY_WORKSPACE_TOKEN" -o notes.download.txt

curl -fsS -X DELETE "$RELAY_WORKSPACE_URL/v1/workspace/files/demo/notes.txt" \
  -H "Authorization: Bearer $RELAY_WORKSPACE_TOKEN"
```
