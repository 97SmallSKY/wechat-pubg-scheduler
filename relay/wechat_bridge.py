"""Use the installed WeChat UI, lock and receipt verification."""

import json
import os
import struct
import subprocess
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

DOCKER = ["/usr/bin/docker", "exec", "-i", "wechat-linux"]
UI_ERRORS = (OSError, RuntimeError, ValueError, subprocess.SubprocessError)


def deliver(job):
    scripts = os.environ.get("RELAY_WECHAT_DIR", "/opt/wechat-automation")
    runner = os.environ.get("RELAY_PUBG_RUNNER", "/opt/wechat-pubg-scheduler/runner")
    ui = SourceFileLoader("relay_ui", scripts + "/watch-replies").load_module()
    report = SourceFileLoader("relay_report_ui", runner + "/wechat_report.py").load_module()
    ui.GROUP = job["group"]
    attempted = False
    with ui.ui_lock():
        try:
            report.open_destination(ui)
            if job["kind"] == "text":
                env = dict(os.environ, WECHAT_UI_LOCK_HELD="1", WECHAT_TARGET_GROUP=ui.GROUP, WECHAT_QUOTED="0")
                attempted = True
                output = ui.command([scripts + "/send-group", "send", job["payload"]], env=env, timeout=35)
                if "WECHAT_GROUP_SEND_VERIFIED" not in output:
                    raise RuntimeError("text receipt missing")
                return {"state": "verified", "receipt": "WECHAT_GROUP_SEND_VERIFIED"}

            payload = Path(job["payload"]).read_bytes()
            width, height = struct.unpack(">II", payload[16:24])
            aspect = width / height
            reference = subprocess.run(DOCKER + ["convert", "png:-", "-resize", "12x16!",
                                                  "-depth", "8", "rgb:-"],
                                       input=payload, stdout=subprocess.PIPE, timeout=15, check=True).stdout
            if ui.visible_text(ui.ocr(327, 543, 530, 91)):
                raise RuntimeError("destination already has a draft")
            compose = "240x259+320+375"
            chat = "300x291+540+240"
            before = report.thumbnail_matches(ui, chat, reference, aspect)
            ui.click(415, 558)
            subprocess.run(DOCKER + ["xclip", "-selection", "clipboard", "-t", "image/png", "-i"],
                           input=payload, stdout=subprocess.DEVNULL, timeout=15, check=True)
            ui.command(ui.wx + ["xdotool", "key", "ctrl+v"])
            time.sleep(0.6)
            if not ui.group_open() or not report.thumbnail_matches(ui, compose, reference, aspect):
                if ui.group_open():
                    ui.click(550, 575)
                    ui.command(ui.wx + ["xdotool", "key", "ctrl+a", "BackSpace"])
                raise RuntimeError("image draft could not be verified")
            attempted = True
            ui.click(850, 650)
            time.sleep(1.2)
            if (not ui.group_open() or report.thumbnail_matches(ui, compose, reference, aspect)
                    or not report.thumbnail_matches(ui, chat, reference, aspect).difference(before)):
                raise RuntimeError("image receipt missing")
            return {"state": "verified", "receipt": "WECHAT_GROUP_IMAGE_VERIFIED"}
        except UI_ERRORS as error:
            # Error details come from this file or contain private chat and command arguments.
            print("WeChat {} phase error={}".format("send" if attempted else "prepare", type(error).__name__),
                  file=sys.stderr)
            return {"state": "review" if attempted else "failed",
                    "error": "需人工核对群内回执" if attempted else "未能准备发送，请核对微信登录、群和草稿"}
        finally:
            try:
                ui.park()
            except UI_ERRORS:
                print("WeChat could not return to its neutral view", file=sys.stderr)


if __name__ == "__main__":
    print(json.dumps(deliver(json.load(sys.stdin)), ensure_ascii=False))
