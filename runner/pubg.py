#!/usr/bin/env python3
"""Read completed Steam PUBG matches and render a local, unsent daily preview."""

import gzip
import json
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

BASE = "https://api.pubg.com/shards/steam"
CST = timezone(timedelta(hours=8))
DEATH_TYPES = {"byplayer", "byzone", "suicide", "logout"}


def fetch(path, api_key=None):
    headers = {"Accept": "application/vnd.api+json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    with urlopen(Request(BASE + path, headers=headers), timeout=12) as response:
        return json.load(response)


def local_time(timestamp):
    if not timestamp.endswith("Z"):
        raise ValueError("expected a UTC timestamp")
    base, _, fraction = timestamp[:-1].partition(".")
    value = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
    return value.replace(tzinfo=timezone.utc,
                         microsecond=int(fraction[:6].ljust(6, "0"))).astimezone(CST)


def fetch_telemetry(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "telemetry-cdn.pubg.com":
        raise ValueError("unexpected PUBG telemetry origin")
    request = Request(url, headers={"Accept-Encoding": "gzip"})
    with urlopen(request, timeout=15) as response:
        if response.headers.get("Content-Encoding") == "gzip":
            with gzip.GzipFile(fileobj=response) as archive:
                return json.load(archive)
        return json.load(response)


def match_record(payload, player_ids, day, telemetry):
    attributes = payload["data"]["attributes"]
    stored = local_time(attributes["createdAt"])
    started = ended = None
    if stored.date() in (day, day + timedelta(days=1)):
        asset = next((entry["attributes"].get("URL") for entry in payload.get("included", ())
                      if entry.get("type") == "asset" and entry["attributes"].get("name") == "telemetry"), None)
        if asset:
            try:
                events = telemetry(asset)
                starts = [local_time(event["_D"]) for event in events if event.get("_T") == "LogMatchStart"]
                ends = [local_time(event["_D"]) for event in events if event.get("_T") == "LogMatchEnd"]
                if starts and ends and min(starts) <= max(ends):
                    started, ended = min(starts), max(ends)
            except (OSError, URLError, KeyError, ValueError):
                pass
    stats = {}
    for entry in payload.get("included", ()):
        if entry.get("type") != "participant":
            continue
        value = entry["attributes"]["stats"]
        if value.get("playerId") in player_ids:
            stats[value["playerId"]] = {
                key: value.get(key) for key in ("kills", "damageDealt", "winPlace", "deathType")
            }
    return {
        "id": payload["data"]["id"], "started_at": started.isoformat() if started else None,
        "ended_at": ended.isoformat() if ended else None, "stored_at": stored.isoformat(),
        "local_day": (ended or stored).date().isoformat(),
        "timing_source": "telemetry" if ended else "api_stored_at",
        "map": attributes.get("mapName"), "mode": attributes.get("gameMode"),
        "stats": stats,
    }


def summarize(matches, player_id):
    ordered = sorted(matches, key=lambda match: match["ended_at"] or match["stored_at"])
    values = [match["stats"][player_id] for match in ordered]
    kills = [stats["kills"] for stats in values]
    damage = [stats["damageDealt"] for stats in values]
    places = [stats["winPlace"] for stats in values]
    deaths = [stats["deathType"] for stats in values]
    recognized_deaths = all(value in DEATH_TYPES or value == "alive" for value in deaths)
    total_kills = sum(kills) if all(value is not None for value in kills) else None
    eliminated = sum(value in DEATH_TYPES for value in deaths) if recognized_deaths else None
    latest = dict(ordered[-1])
    latest["stats"] = values[-1]
    all_timed = all(match["ended_at"] is not None for match in ordered)
    return {
        "matches": len(ordered),
        "wins": places.count(1) if all(value is not None for value in places) else None,
        "kills": total_kills,
        "eliminated_matches": eliminated,
        "kd_estimate": round(total_kills / eliminated, 2)
        if total_kills is not None and eliminated else None,
        "average_damage": round(sum(damage) / len(damage), 1)
        if all(value is not None for value in damage) else None,
        "first_start": min(match["started_at"] for match in ordered) if all_timed else None,
        "last_end": ordered[-1]["ended_at"] if all_timed else None,
        "latest": latest,
        "match_ids": [match["id"] for match in ordered],
    }


def collect(names, day, api_key, request=fetch, telemetry=fetch_telemetry):
    query = urlencode({"filter[playerNames]": ",".join(names)})
    try:
        data = request("/players?" + query, api_key)["data"]
    except HTTPError as error:
        if error.code != 404:
            raise
        data = []
    indexed = {player["attributes"]["name"].casefold(): player for player in data}
    matched = {name: indexed.get(name.casefold()) for name in names}
    owners = {}
    for name, player in matched.items():
        if player is None:
            continue
        for match in player["relationships"]["matches"]["data"]:
            owners.setdefault(match["id"], set()).add(name)

    by_player = {name: [] for name in names}
    missing = {name: [] for name in names}
    player_ids = {player["id"] for player in matched.values() if player}
    for match_id, names_in_match in owners.items():
        try:
            record = match_record(request("/matches/" + quote(match_id, safe="")), player_ids, day, telemetry)
        except HTTPError as error:
            if error.code != 404:
                raise
            for name in names_in_match:
                missing[name].append(match_id)
            continue
        if record["local_day"] != day.isoformat():
            continue
        for name in names_in_match:
            if matched[name]["id"] in record["stats"]:
                by_player[name].append(record)
            else:
                missing[name].append(match_id)

    players = []
    for name in names:
        player = matched[name]
        row = {"name": name, "missing_match_details": missing[name]}
        if player is None:
            row["status"] = "not_found"
        elif by_player[name]:
            row["status"] = "partial" if missing[name] else "records"
            row["summary"] = summarize(by_player[name], player["id"])
        else:
            row["status"] = "partial" if missing[name] else "no_records"
        players.append(row)
    return players


def player_paragraph(row):
    name, state = row["name"], row["status"]
    if state == "not_found":
        return name + "：Steam 玩家未匹配。"
    if "summary" not in row:
        return name + ("：部分对局详情缺失，无法确认今日战绩。" if state == "partial"
                       else "：今日未查到已完成对局。")
    data = row["summary"]
    latest = data["latest"]
    stats = latest["stats"]
    number = lambda value: "—" if value is None else str(value)
    eliminated = data["eliminated_matches"]
    kd = "零淘汰" if eliminated == 0 else number(data["kd_estimate"])
    comment = "下一把先明确落点和转移路线，让报点与集火跟上。"
    if stats["winPlace"] == 1:
        comment = "吃鸡可喜，下一把把赢圈的转移节奏复制出来。"
    elif (stats["damageDealt"] or 0) >= 200 and stats["kills"] in (0, 1):
        comment = "有伤害没转成击杀，下把补枪和集火别慢半拍。"
    clock = lambda value: value[11:16]
    span = "对局起止不全"
    if data["first_start"]:
        span_start = clock(data["first_start"])
        if data["first_start"][:10] != latest["local_day"]:
            span_start = data["first_start"][5:10] + " " + span_start
        span = span_start + "–" + clock(data["last_end"])
    latest_time = clock(latest["ended_at"] or latest["stored_at"])
    if not latest["ended_at"]:
        latest_time += "入库"
    return ("{} {}，{}局{}鸡，击杀{}，K/D估算{}，场均伤害{}。"
            "末条{} 第{}名，{}杀／{}伤。{}{}").format(
        name, span, data["matches"], number(data["wins"]),
        number(data["kills"]), kd, number(data["average_damage"]), latest_time,
        number(stats["winPlace"]), number(stats["kills"]), number(stats["damageDealt"]), comment,
        " 部分对局详情缺失。" if state == "partial" else "")


def pack_paragraphs(paragraphs, capacity=400):
    messages = []
    for paragraph in paragraphs:
        if len(paragraph) > capacity:
            raise ValueError("a whole paragraph exceeds the preview message budget")
        if messages and len(messages[-1]) + 2 + len(paragraph) <= capacity:
            messages[-1] += "\n\n" + paragraph
        else:
            messages.append(paragraph)
    if len(messages) > 3:
        raise ValueError("the preview would require more than three messages")
    return messages
