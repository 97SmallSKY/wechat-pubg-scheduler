---
name: relay-wechat
description: Calls the Relay API to send WeChat group text and PNGs, inspect delivery receipts, or validate Chinese idiom chains. Use when asked to work with Relay, send to an authorized WeChat group, or use the Relay 成语接龙 API.
---

# Relay 微信 API

从环境读取 `RELAY_URL` 和 `RELAY_TOKEN`。凭据由开发者单独配置。请求用
`Authorization: Bearer $RELAY_TOKEN`，日志和回答只记录群别名、发送 ID 及状态。

## 调用

- 用 `GET /v1/groups` 查看当前凭据可发送的群别名。使用用户指定且已获准的群。
- 发单行文本用 `POST /v1/wechat/text`。先上传或生成 PNG，再用返回的图片 ID 调用 `POST /v1/wechat/image`。
- 发送请求只在用户要求实际发送时提交。每条业务消息使用独立的 `Idempotency-Key`。同一次发送重试时复用原键和原参数。
- `202` 表示已入队。用 `GET /v1/deliveries/{id}` 查回执，`verified` 表示已核验。遇到 `review` 时提示用户到群里核对。
- 成语接龙调用 `POST /v1/idioms/chain`。传入上一条成语、可选候选成语和已使用列表，按返回的 `valid` 和 `next` 回答。

文本、PNG、接龙及回执的命令见 [curl 示例](references/curl.md)。
