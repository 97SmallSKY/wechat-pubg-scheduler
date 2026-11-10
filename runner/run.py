#!/usr/bin/env python3
"""Claim at most one preview from an owner-private Sites deployment."""
import json
import os
import sys
from datetime import datetime
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

import pubg


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def site_post(origin, route, payload, site_token, runner_token):
    request = Request(origin + "/api/runner/" + route, data=json.dumps(payload).encode(),
                      headers={
                          "Content-Type": "application/json",
                          "OAI-Sites-Authorization": "Bearer " + site_token,
                          "Authorization": "Bearer " + runner_token,
                      })
    with build_opener(NoRedirect()).open(request, timeout=12) as response:
        return json.load(response)


def preview(job, api_key):
    names = [row["steam"] for row in job["config"]["players"]]
    day = datetime.strptime(job["report_day"], "%Y-%m-%d").date()
    players = pubg.collect(names, day, api_key)
    relevant = {player["name"] for player in players if "summary" in player}
    mentions = list(dict.fromkeys(row["wechat"] for row in job["config"]["players"]
                                  if row["wechat"] and row["steam"] in relevant))
    paragraphs = (["{} PUBG 已完成对局".format(day.isoformat())]
                  + [pubg.player_paragraph(row) for row in players]
                  + ["时段来自已记录对局。缺少起止时按入库日统计。K/D 按淘汰场次估算。"])
    return {
        "messages": pubg.pack_paragraphs(paragraphs, capacity=500),
        "players": players,
        "mentions": mentions,
    }


def main():
    config = [os.environ.get(name) for name in
              ("SITES_ORIGIN", "SITES_SERVICE_TOKEN", "RUNNER_TOKEN", "PUBG_API_KEY")]
    if not all(config) or not config[0].startswith("https://") or config[0].endswith("/"):
        sys.exit("Set SITES_ORIGIN (HTTPS, no trailing slash), SITES_SERVICE_TOKEN, RUNNER_TOKEN and PUBG_API_KEY.")
    origin, site_token, runner_token, api_key = config
    try:
        job = site_post(origin, "claim", {}, site_token, runner_token)["job"]
        if job is None:
            return
        try:
            result = preview(job, api_key)
            status = "previewed"
        except (OSError, URLError, KeyError, ValueError) as error:
            code = getattr(error, "code", type(error).__name__)
            result = {"error": "PUBG 查询失败（{}）。请检查 AWS 日志和接口状态。".format(code)}
            status = "failed"
        site_post(origin, "result", {"id": job["id"], "status": status, "result": result},
                  site_token, runner_token)
        print("Run {} {}".format(job["id"], status))
    except (OSError, URLError, KeyError, ValueError) as error:
        sys.exit("Sites request failed ({})".format(getattr(error, "code", type(error).__name__)))


if __name__ == "__main__":
    main()
