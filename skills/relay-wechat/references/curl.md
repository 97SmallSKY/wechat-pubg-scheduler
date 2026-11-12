# Relay curl 示例

把 `RELAY_URL` 设置成部署方提供的地址，把 `RELAY_TOKEN` 设置成自己的 Bearer 凭据。下面的 `test` 是测试群别名。发送示例会实际向该群提交消息，执行前替换示例正文、图片和幂等键。

## 发群文本

```sh
curl -fsS "$RELAY_URL/v1/wechat/text" \
  -H "Authorization: Bearer $RELAY_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: dev-demo-001-text' \
  --data '{"group":"test","text":"Relay API 联调测试"}'
```

## 上传并发 PNG

上传返回图片的 `id`。将它填入发送请求的 `image_id`。

```sh
curl -fsS "$RELAY_URL/v1/images/upload" \
  -H "Authorization: Bearer $RELAY_TOKEN" \
  -H 'Content-Type: image/png' \
  --data-binary @card.png

curl -fsS "$RELAY_URL/v1/wechat/image" \
  -H "Authorization: Bearer $RELAY_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: dev-demo-001-image' \
  --data '{"group":"test","image_id":"填写上传返回的 id"}'
```

也可以调用 `POST /v1/images/generate`，例如提交
`{"title":"活动战报","metrics":[{"label":"已参与","value":8}]}`，再用返回的 `id` 发送。

## 成语接龙

```sh
curl -fsS "$RELAY_URL/v1/idioms/chain" \
  -H "Authorization: Bearer $RELAY_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"previous":"云开见日","candidate":"日新月异","used":[]}'
```

## 查发送回执

将发送请求返回的 `id` 填入 `DELIVERY_ID`。

```sh
curl -fsS "$RELAY_URL/v1/deliveries/$DELIVERY_ID" \
  -H "Authorization: Bearer $RELAY_TOKEN"
```
