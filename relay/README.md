# Relay 微信基础 API

开发者使用独立 Bearer 凭据。群用别名表示，凭据仅能向显式授权的群发送。图片与发送记录按凭据所属账号隔离。

## 接口

| 方法 | 路径 | 输入与结果 |
| --- | --- | --- |
| GET | `/healthz` | 服务状态与版本，可匿名读取 |
| GET | `/v1/groups` | 返回当前凭据可发送的群别名 |
| POST | `/v1/wechat/text` | `group` 和 `text`。正文单行，最多 120 字，返回发送 ID |
| POST | `/v1/images/generate` | `title`、可选 `text`、可选 `metrics`，从结构化数据生成 PNG 海报 |
| POST | `/v1/images/upload` | 以 `image/png` 上传，最多 2 MiB，返回图片 ID 和下载路径 |
| GET | `/v1/images/{id}` | 下载生成或上传并标准化后的 PNG |
| POST | `/v1/wechat/image` | `group` 和 `image_id`，返回发送 ID |
| GET | `/v1/deliveries/{id}` | 查询发送状态和已核验的回执 |
| POST | `/v1/idioms/chain` | `previous`、可选 `candidate` 和 `used`，按首尾同字校验并给出最多 5 个候选 |

发送接口需要 `Idempotency-Key`。对同一次发送，重试时使用原键和原参数，返回同一个发送 ID。不同参数复用原键返回 409。202 表示已入队。查询状态有 `queued`、`sending`、`verified`、`failed`、`review`。回执待核对时应先在群里确认，避免用新键重复提交。

海报标题最多 20 字，正文最多 210 字且折行后最多 10 行，指标最多 6 项，每项包含 `label` 和 `value`。图片统一输出为 768×960 PNG。上传图像等比缩放并补边，以适配微信群里的预览和回执核对。

成语接口要求 `previous` 为词库中的四字成语。未传 `candidate` 时 `valid` 返回 `null`。排除上一条和 `used` 中已使用的词，候选列表可能为空。词库为 [chinese-xinhua 的四字成语提取](https://github.com/pwxcoo/chinese-xinhua/blob/fe6d6c2e8baa82187f4c96bbe042e43f96c05666/data/idiom.json)，[MIT 许可](IDIOMS-LICENSE.txt)。

## 调用示例

Codex 开发者也可以使用仓库里的 [Relay 微信 Skill](../skills/relay-wechat/SKILL.md)。

设置 `RELAY_URL` 为公网 API 地址，`RELAY_TOKEN` 为自己的凭据。固定 IP 部署支持 `http://<公网 IP>:19016` 和 `https://<公网 IP>`，两者使用相同的 Bearer 鉴权。HTTP 会明文传输凭据和内容，HTTPS 使用自动续期的公网证书。所有示例都使用虚构正文，`test` 需替换为实际授权的群别名。

```sh
curl -fsS "$RELAY_URL/v1/groups" -H "Authorization: Bearer $RELAY_TOKEN"

curl -fsS "$RELAY_URL/v1/wechat/text" \
  -H "Authorization: Bearer $RELAY_TOKEN" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: event-42-text' \
  --data '{"group":"test","text":"今晚 21:00 活动开始"}'

curl -fsS "$RELAY_URL/v1/images/generate" \
  -H "Authorization: Bearer $RELAY_TOKEN" -H 'Content-Type: application/json' \
  --data '{"title":"活动战报","text":"今晚的统计","metrics":[{"label":"已参与","value":8}]}'

curl -fsS "$RELAY_URL/v1/images/upload" \
  -H "Authorization: Bearer $RELAY_TOKEN" -H 'Content-Type: image/png' \
  --data-binary @card.png

curl -fsS "$RELAY_URL/v1/wechat/image" \
  -H "Authorization: Bearer $RELAY_TOKEN" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: event-42-image' \
  --data '{"group":"test","image_id":"填写上一步返回的 id"}'

curl -fsS "$RELAY_URL/v1/deliveries/$DELIVERY_ID" \
  -H "Authorization: Bearer $RELAY_TOKEN"

curl -fsS "$RELAY_URL/v1/idioms/chain" \
  -H "Authorization: Bearer $RELAY_TOKEN" -H 'Content-Type: application/json' \
  --data '{"previous":"云开见日","candidate":"日新月异","used":[]}'
```

## 服务器

Python 3.6+。应用只监听本机 `127.0.0.1:9016`，由公网入口转发。图片渲染使用 Docker。微信发送复用现有的 `watch-replies`、`send-group`、`wechat_report.py` 和微信窗口锁。服务器从 `/opt/wechat-automation/archive.env` 读取 `WECHAT_ARCHIVE_GROUPS` 的别名配置。发送功能依赖服务器的微信登录状态。

1. 构建渲染器 `docker build -f deploy/relay-image.Dockerfile -t relay-image:2 .`。
2. 安装 `relay/` 到 `/opt/relay-wechat-api/current/`。创建私有状态目录，并在 `/opt/relay-wechat-api/relay.env` 设置 `RELAY_STATE=/opt/relay-wechat-api/state`、`RELAY_VERSION` 为提交版本。
3. 在安装目录执行 `python3 -m relay.keys /opt/relay-wechat-api/state/keys.json issue developer-name test`。命令仅在创建时输出凭据，服务器只保存摘要。使用相同名称重新签发会轮换凭据，使用 `revoke developer-name` 会撤销该凭据。
4. 安装并启动 `deploy/relay-wechat-api.service`。使用已有的 HTTPS 反向代理，或安装 `deploy/relay-wechat-tunnel.service` 用 Cloudflare Quick Tunnel 提供开发联调入口。该公网地址会在隧道进程重启后改变。 [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
5. 公网验证 `GET /healthz`、无凭据拒绝、凭据群权限与测试群实际回执。

### 固定公网 IP

在云防火墙放行入站 TCP 19016 供 HTTP API 使用。现有 HTTPS 使用 TCP 443，证书签发和续期使用 TCP 80。将 `deploy/relay-wechat.Caddyfile` 安装到 `/opt/relay-wechat-api/Caddyfile`，在 `/opt/relay-wechat-api/public.env` 设置 `RELAY_PUBLIC_IP`。创建同目录下的 `caddy-data` 和 `caddy-config`，保留证书续期状态。拉取 `caddy:2-alpine` 并启动 `deploy/relay-wechat-https.service`。Caddy 使用 Let's Encrypt 短期 IP 证书并自动续期。 [Let's Encrypt IP 地址证书](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability)

在仓库根目录执行 `python3 -m unittest discover -s tests` 与 `npm test`。


### 数据库与文件工作区

[工作区 API 与 curl 示例](../skills/relay-workspace/references/api.md)提供独立开发库和工作目录的 SQL 与文件操作。工作区使用 HTTPS 和单独的凭据。可用 `python3 -m relay.keys /opt/relay-wechat-api/state/keys.json issue developer-workspace --workspace` 签发。普通微信凭据的群授权不授予工作区权限。

1. 在现有 PostgreSQL 上执行 `deploy/relay-workspace.sql`，通过 psql 变量 `workspace_password` 传入新密码。该脚本创建 `relay_developer` 和独立登录角色 `relay_workspace`。
2. 在 PostgreSQL 的 `pg_hba.conf` 通用规则之前，为 `relay_workspace` 设置允许规则，只允许 Relay 主机从指定源地址连接 `relay_developer`，并拒绝该角色其他 TCP 和 Unix socket 连接。使用 `pg_hba_file_rules` 检查后重新加载。
3. 使用 `deploy/relay-workspace-requirements.txt` 将数据库驱动安装到 Relay 专用目录。用只允许服务账号读取的 `/opt/relay-wechat-api/workspace.env` 配置 `PYTHONPATH` 和 `RELAY_WORKSPACE_DSN`。后者连接本机 PostgreSQL 端口，使用新库和新角色。
4. 更新 Caddy 和 Relay 服务。文件工作目录为 `$RELAY_STATE/workspace-files`，由服务创建。
