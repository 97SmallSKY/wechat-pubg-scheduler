# PUBG 微信日报控制台

在私有 ChatGPT Site 配置北京时间每日预览、Steam 名单和微信群成员映射。AWS 用 systemd 拉取任务，查询 PUBG 官方 API，把日报草稿与运行状态回传到控制台。任务由 AWS 运行，Mac 可离线。

当前版本支持 **定时预览与手动预览**。默认北京时间 **23:00，暂停**。首版只生成草稿。实际群发需要先验收目标群、原生 @ 和发送回执。

| 位置 | 用途 |
| --- | --- |
| `ui/` | 任务配置、执行器状态、历史预览 |
| `worker/`、`drizzle/` | Sites Worker、D1 配置与运行队列 |
| `runner/` | AWS 执行器、战绩汇总与自然段排版 |
| `deploy/` | systemd 单元与无密钥环境示例 |

## 验证

需要 Node.js 22.13+、Python 3.6+。运行前复制示例 manifest，已有真实 manifest 时保留它。

```sh
npm test
test -f .openai/hosting.json || cp .openai/hosting.example.json .openai/hosting.json
npm run build
python3 -m unittest discover -s tests
```

## 私有部署

1. 建立仅所有者可访问的 ChatGPT Site。将其项目 ID 写入本地 `.openai/hosting.json`，保留 `"d1": "DB"`。在 Sites 设置秘密变量 `RUNNER_TOKEN`，使用独立的随机值。通过 Sites 工作流推送构建源码并部署，发布时应用 D1 迁移。
2. 在 AWS 将 `runner/` 放在 `/opt/wechat-pubg-scheduler/runner/`。创建仅服务账户可读的 `/opt/wechat-pubg-scheduler/runner.env`，参见 `deploy/runner.env.example`。`SITES_ORIGIN` 为部署的 HTTPS 站点，`SITES_SERVICE_TOKEN` 取自该私有 Site 的服务访问凭据，`RUNNER_TOKEN` 与 Sites 秘密变量一致。PUBG 密钥沿用 AWS 的 `/opt/wechat-automation/pubg-api.env`，由 systemd 读取。
3. 将两个 `deploy/pubg-preview.*` 单元安装到 `/etc/systemd/system/`。先执行 `systemd-analyze verify` 和 `systemctl daemon-reload`。保存玩家名单，点击「立即预览」，用 `systemctl start pubg-preview.service` 跑一次，核对网页状态。
4. 预览验证后，可用 `systemctl enable --now pubg-preview.timer` 启动每分钟轮询，再在网页启用每日预览。暂停每日预览可以继续手动查询。要停止 AWS 轮询，可用 `systemctl disable --now pubg-preview.timer`。

同一个北京时间日期最多创建一次每日任务。执行器在设定分钟领取任务，离线或忙碌错过该分钟时，当天不自动补跑。手动预览使用提交时保存的配置。运行详情区分排队、查询、已生成预览和失败。

Steam 名单每轮最多 10 人，合并为一次带密钥的玩家查询。对局详情和 Telemetry 不计入密钥额度。官方接口只返回可见的已完成对局，时段优先用 Telemetry。若缺起止时间，以入库日作为统计依据。K/D 为总击杀除以以淘汰结束的场数估算。仅在报告有统计且保存了微信昵称时列为拟提及。 [PUBG 官方接口限额](https://documentation.pubg.com/en/rate-limits.html)

## 提交 PR

Fork 后从 `main` 创建分支，运行上面的验证，再向本仓库的 `main` 发 Pull Request。描述改动目的与验证结果。请用虚构玩家、群名和凭据编写样例。部署 manifest、聊天数据、运行记录和密钥请留在私有环境。

## 微信基础 API

独立的 Relay 服务提供群文本、PNG 生成与发送、成语接龙和发送回执。参见 [Relay API 接入文档](relay/README.md)。
