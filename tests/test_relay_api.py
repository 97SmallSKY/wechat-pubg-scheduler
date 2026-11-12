import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import Mock, patch

from relay import images
from relay.keys import digest
from relay.server import Handler, Relay, Server


class RelayAPITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.keys = cls.root / "keys.json"
        cls.credentials = {
            "alice": {"digest": digest("alice-token"), "groups": ["test"]},
            "bob": {"digest": digest("bob-token"), "groups": []},
        }
        cls.write_keys(cls.credentials)
        cls.service = Relay(cls.root, cls.keys, {"test": "虚构测试群", "other": "虚构其他群"})
        cls.server = Server(("127.0.0.1", 0), Handler)
        cls.server.relay = cls.service
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()
        cls.tmp.cleanup()

    @classmethod
    def write_keys(cls, values):
        cls.keys.write_text(json.dumps(values), encoding="utf-8")

    def setUp(self):
        self.write_keys(self.credentials)
        with self.service.db() as db:
            db.execute("DELETE FROM deliveries")

    def http(self, path, body=None, token="alice-token", key=None):
        headers = {"Authorization": "Bearer " + token} if token else {}
        if key:
            headers["Idempotency-Key"] = key
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json"
        elif isinstance(body, bytes):
            headers["Content-Type"] = "image/png"
        request = Request("http://127.0.0.1:" + str(self.server.server_port) + path, body, headers)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            data = response.read()
            if response.headers.get_content_type() == "application/json":
                data = json.loads(data.decode())
            return response.code, data

    def test_health_and_group_permissions(self):
        self.assertEqual(self.http("/healthz", token=None)[0], 200)
        self.assertEqual(self.http("/v1/groups", token=None)[0], 401)
        self.assertEqual(self.http("/v1/groups"), (200, {"groups": ["test"]}))
        self.assertEqual(self.http("/v1/wechat/text", {"group": "other", "text": "test"}, key="no")[0], 403)
        self.assertEqual(self.http("/v1/wechat/text", {"group": "test", "text": "test"},
                                   token="bob-token", key="no")[0], 403)

    def test_idiom_chain_valid_invalid_and_repeat(self):
        cases = [("日新月异", [], True), ("一心一意", [], False),
                 ("日新月异", ["日新月异"], False), ("日不是词", [], False)]
        for candidate, used, valid in cases:
            status, result = self.http("/v1/idioms/chain", {"previous": "云开见日", "candidate": candidate, "used": used})
            self.assertEqual(status, 200)
            self.assertIs(result["valid"], valid)
            self.assertTrue(result["next"])
            self.assertTrue(all(word.startswith("日") and word not in used for word in result["next"]))
        self.assertEqual(self.http("/v1/idioms/chain", {"previous": "这里没有"})[0], 400)

    def test_text_idempotency_and_owner_only_receipt(self):
        body = {"group": "test", "text": "测试"}
        self.assertEqual(self.http("/v1/wechat/text", body)[0], 400)
        self.assertEqual(self.http("/v1/wechat/text", dict(body, text="两\n行"), key="bad")[0], 400)
        status, ticket = self.http("/v1/wechat/text", body, key="text")
        self.assertEqual(status, 202)
        self.assertEqual(self.http("/v1/wechat/text", body, key="text"), (202, ticket))
        self.assertEqual(self.http("/v1/wechat/text", dict(body, text="改"), key="text")[0], 409)
        path = "/v1/deliveries/" + ticket["id"]
        self.assertEqual(self.http(path, token="bob-token")[0], 404)
        self.assertEqual(self.http(path)[1]["state"], "queued")
        sender = Mock(return_value={"state": "verified", "receipt": "WECHAT_GROUP_SEND_VERIFIED"})
        self.assertTrue(self.service.send_next(sender))
        self.assertFalse(self.service.send_next(sender))
        sender.assert_called_once_with({"group": "虚构测试群", "kind": "text", "payload": "测试"})
        self.assertEqual(self.http(path)[1]["receipt"], "WECHAT_GROUP_SEND_VERIFIED")
        self.assertEqual(self.http("/v1/wechat/text", body, key="text"), (202, ticket))
        self.assertFalse(self.service.send_next(sender))

    def test_image_api_and_owner_isolation(self):
        png = images.PNG + b"fixture"
        with patch.object(images, "render", return_value=png) as renderer:
            status, result = self.http("/v1/images/generate", {"title": "测试 <图>", "metrics": [{"label": "人数", "value": 2}]})
            self.assertEqual(status, 201)
            self.assertIn(b"&lt;", renderer.call_args[0][2])
        self.assertEqual(self.http(result["path"]), (200, png))
        self.assertEqual(self.http(result["path"], token="bob-token")[0], 404)
        self.assertEqual(self.http("/v1/images/upload", b"not a png")[0], 400)
        with patch.object(images, "normalize", return_value=png):
            self.assertEqual(self.http("/v1/images/upload", png)[0], 201)
        status, ticket = self.http("/v1/wechat/image", {"group": "test", "image_id": result["id"]}, key="image")
        self.assertEqual(status, 202)
        sender = Mock(return_value={"state": "review", "error": "核对回执"})
        self.assertTrue(self.service.send_next(sender))
        self.assertEqual(Path(sender.call_args[0][0]["payload"]).read_bytes(), png)
        self.assertEqual(self.http("/v1/deliveries/" + ticket["id"])[1]["state"], "review")
        self.assertFalse(self.service.send_next(sender))

    def test_revoke_queued_key_and_restart_uncertain_send(self):
        body = {"group": "test", "text": "测试"}
        _, first = self.http("/v1/wechat/text", body, key="revoke")
        self.write_keys({"bob": self.credentials["bob"]})
        sender = Mock()
        self.assertTrue(self.service.send_next(sender))
        sender.assert_not_called()
        self.write_keys(self.credentials)
        self.assertEqual(self.service.receipt("alice", first["id"])["state"], "failed")
        _, second = self.http("/v1/wechat/text", body, key="interrupted")
        with self.service.db() as db:
            db.execute("UPDATE deliveries SET state='sending' WHERE id=?", (second["id"],))
        restarted = Relay(self.root, self.keys, self.service.groups)
        self.assertEqual(restarted.receipt("alice", second["id"])["state"], "review")
        self.assertFalse(restarted.send_next(sender))


if __name__ == "__main__":
    unittest.main()
