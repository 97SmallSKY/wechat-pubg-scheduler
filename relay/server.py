"""Small authenticated HTTP API for WeChat delivery, PNGs and idiom chaining."""

import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn

from . import idioms, images
from .keys import digest

LOG = logging.getLogger(__name__)
ID = r"[0-9a-f]{32}"
IDEMPOTENCY_KEY = re.compile(r"[a-zA-Z0-9._-]{1,100}\Z")


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


class APIError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Relay:
    def __init__(self, state, keys, groups, version="local"):
        self.state = state
        self.keys = keys
        self.groups = groups
        self.version = version
        (state / "images").mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS images(
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS deliveries(
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_key TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, group_id TEXT NOT NULL, kind TEXT NOT NULL,
                    payload TEXT, state TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL,
                    receipt TEXT, error TEXT, UNIQUE(owner, request_key)
                );
                CREATE INDEX IF NOT EXISTS delivery_queue ON deliveries(state);
            """)
            db.execute("""UPDATE deliveries SET state='review', payload=NULL, updated=?,
                          error='服务重启时发送未完成，请人工核对' WHERE state='sending'""", (stamp(),))

    @contextmanager
    def db(self):
        db = sqlite3.connect(str(self.state / "relay.sqlite3"), timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def authenticate(self, header):
        if header and header.startswith("Bearer "):
            hashed = digest(header[7:])
            for owner, entry in json.loads(self.keys.read_text(encoding="utf-8")).items():
                if hmac.compare_digest(hashed, entry["digest"]):
                    return owner, entry["groups"]
        raise APIError(401, "需要有效的 Bearer 凭据")

    def save_image(self, owner, png):
        image = uuid.uuid4().hex
        (self.state / "images" / (image + ".png")).write_bytes(png)
        with self.db() as db:
            db.execute("INSERT INTO images VALUES(?,?)", (image, owner))
        return {"id": image, "path": "/v1/images/" + image}

    def image(self, owner, image):
        if isinstance(image, str) and re.fullmatch(ID, image):
            with self.db() as db:
                if db.execute("SELECT 1 FROM images WHERE id=? AND owner=?", (image, owner)).fetchone():
                    return self.state / "images" / (image + ".png")
        raise APIError(404, "图片不存在")

    def enqueue(self, owner, allowed, kind, body, key):
        if not key or not IDEMPOTENCY_KEY.fullmatch(key):
            raise APIError(400, "需要有效的 Idempotency-Key")
        group = body.get("group")
        if not isinstance(group, str) or group not in allowed or group not in self.groups:
            raise APIError(403, "凭据未获准向该群发送")
        if kind == "text":
            payload = images.text(body.get("text"), "微信正文", 120).strip()
            if "\n" in payload or "\t" in payload:
                raise APIError(400, "微信正文需要单行")
        else:
            payload = body.get("image_id")
            self.image(owner, payload)
        fingerprint = hashlib.sha256(encode([kind, group, payload]).encode("utf-8")).hexdigest()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT id,fingerprint FROM deliveries WHERE owner=? AND request_key=?",
                               (owner, key)).fetchone()
            if prior:
                if prior["fingerprint"] != fingerprint:
                    raise APIError(409, "该幂等键已用于另一个发送请求")
                return {"id": prior["id"]}
            if db.execute("SELECT count(*) FROM deliveries WHERE state='queued'").fetchone()[0] >= 30:
                raise APIError(429, "发送队列已满，请稍后重试")
            identifier = uuid.uuid4().hex
            created = stamp()
            db.execute("""INSERT INTO deliveries(id,owner,request_key,fingerprint,group_id,kind,
                               payload,state,created,updated) VALUES(?,?,?,?,?,?,?,'queued',?,?)""",
                       (identifier, owner, key, fingerprint, group, kind, payload, created, created))
        return {"id": identifier}

    def receipt(self, owner, identifier):
        with self.db() as db:
            row = db.execute("""SELECT id, group_id AS 'group', kind, state, created, updated, receipt, error
                                FROM deliveries WHERE id=? AND owner=?""", (identifier, owner)).fetchone()
        if row is None:
            raise APIError(404, "发送记录不存在")
        return dict(row)

    def send_next(self, deliver):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM deliveries WHERE state='queued' ORDER BY rowid LIMIT 1").fetchone()
            if not row:
                return False
            db.execute("UPDATE deliveries SET state='sending', updated=? WHERE id=?", (stamp(), row["id"]))
        allowed = json.loads(self.keys.read_text(encoding="utf-8")).get(row["owner"], {}).get("groups", [])
        group = self.groups.get(row["group_id"])
        if group is None or row["group_id"] not in allowed:
            outcome = {"state": "failed", "error": "发送凭据或群授权已撤销"}
        else:
            payload = row["payload"] if row["kind"] == "text" else str(self.image(row["owner"], row["payload"]))
            outcome = deliver({"group": group, "kind": row["kind"], "payload": payload})
        with self.db() as db:
            db.execute("""UPDATE deliveries SET state=?,updated=?,receipt=?,error=?,payload=NULL WHERE id=?""",
                       (outcome["state"], stamp(), outcome.get("receipt"), outcome.get("error"), row["id"]))
        LOG.info("delivery=%s kind=%s state=%s", row["id"], row["kind"], outcome["state"])
        return True

    @staticmethod
    def deliver(job):
        env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "PYTHONIOENCODING",
                                                "RELAY_WECHAT_DIR", "RELAY_PUBG_RUNNER") if key in os.environ}
        try:
            result = subprocess.run([sys.executable, "-m", "relay.wechat_bridge"],
                                    input=encode(job).encode("utf-8"), stdout=subprocess.PIPE,
                                    env=env, timeout=100, check=True)
            return json.loads(result.stdout.decode("utf-8"))
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            LOG.warning("wechat bridge result unavailable: %s", type(error).__name__)
            return {"state": "review", "error": "微信发送状态不明，请人工核对"}

    def run_worker(self):
        while True:
            try:
                if self.send_next(self.deliver):
                    continue
            except (OSError, sqlite3.OperationalError) as error:
                LOG.error("delivery worker: %s", type(error).__name__)
            time.sleep(0.5)


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    server_version = "Relay"
    sys_version = ""

    def log_message(self, message, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def respond(self, status, data):
        binary = isinstance(data, bytes)
        content = data if binary else encode(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "image/png" if binary else "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def route(self):
        service = self.server.relay
        path = self.path
        method = self.command
        if method == "GET" and path == "/healthz":
            return 200, {"status": "ok", "version": service.version}
        owner, groups = service.authenticate(self.headers.get("Authorization"))
        if method == "GET":
            if path == "/v1/groups":
                return 200, {"groups": [group for group in groups if group in service.groups]}
            image = re.fullmatch("/v1/images/(" + ID + ")", path)
            if image:
                return 200, service.image(owner, image[1]).read_bytes()
            delivery = re.fullmatch("/v1/deliveries/(" + ID + ")", path)
            if delivery:
                return 200, service.receipt(owner, delivery[1])
        elif method == "POST":
            raw_png = path == "/v1/images/upload"
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= (images.MAX_PNG if raw_png else 16384):
                raise APIError(400, "请求体为空或超出大小限制")
            content_type = self.headers.get_content_type()
            if content_type != ("image/png" if raw_png else "application/json"):
                raise APIError(415, "请求体需要 image/png" if raw_png else "请求体需要 application/json")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise APIError(400, "请求体不完整")
            if raw_png:
                return 201, service.save_image(owner, images.normalize(raw))
            body = json.loads(raw.decode("utf-8"))
            if not isinstance(body, dict):
                raise APIError(400, "请求体需要 JSON 对象")
            if path == "/v1/images/generate":
                return 201, service.save_image(owner, images.generate(body))
            if path == "/v1/idioms/chain":
                return 200, idioms.chain(body)
            if path in ("/v1/wechat/text", "/v1/wechat/image"):
                return 202, service.enqueue(owner, groups, path.rsplit("/", 1)[-1],
                                            body, self.headers.get("Idempotency-Key"))
        raise APIError(404, "接口不存在")

    def request(self):
        try:
            try:
                status, data = self.route()
            except APIError as error:
                status, data = error.status, {"error": str(error)}
            except (json.JSONDecodeError, UnicodeDecodeError):
                status, data = 400, {"error": "请求体不是有效 UTF-8 JSON"}
            except ValueError as error:
                status, data = 400, {"error": str(error)}
            except (OSError, sqlite3.OperationalError) as error:
                LOG.error("request failed: %s", type(error).__name__)
                status, data = 503, {"error": "服务暂时不可用"}
            self.respond(status, data)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True

    do_GET = do_POST = request


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    state = Path(os.environ["RELAY_STATE"])
    keys = Path(os.environ.get("RELAY_KEYS", str(state / "keys.json")))
    groups = json.loads(os.environ.get("WECHAT_ARCHIVE_GROUPS", "{}"))
    service = Relay(state, keys, groups, os.environ.get("RELAY_VERSION", "local"))
    server = Server(("127.0.0.1", int(os.environ.get("RELAY_PORT", "9016"))), Handler)
    server.relay = service
    threading.Thread(target=service.run_worker, daemon=True).start()
    LOG.info("Relay API release=%s port=%s", service.version, server.server_port)
    server.serve_forever()


if __name__ == "__main__":
    main()
