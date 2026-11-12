"""Render cards and normalize PNGs for the existing WeChat thumbnail verifier."""

import os
import struct
import subprocess
from xml.sax.saxutils import escape

PNG = b"\x89PNG\r\n\x1a\n"
MAX_PNG = 2 * 1024 * 1024


def text(value, label, limit, optional=False):
    if (not isinstance(value, str) or len(value) > limit or (not optional and not value.strip())
            or any((ord(c) < 32 and c not in "\n\t") or 0xd800 <= ord(c) <= 0xdfff
                   or c in "\ufffe\uffff" for c in value)):
        raise ValueError("{} 需要有效文本，最多 {} 字".format(label, limit))
    return value


def render(program, arguments, payload):
    command = [
        "/usr/bin/docker", "run", "--rm", "-i", "--network", "none", "--read-only",
        "--user", "65534:65534", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "24", "--memory", "160m", "--cpus", "1",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m,mode=1777",
        "--entrypoint", "/usr/bin/timeout", os.environ.get("RELAY_IMAGE", "relay-image:2"),
        "18", program,
    ]
    try:
        result = subprocess.run(command + arguments, input=payload, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=20, check=True).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("无法渲染或读取 PNG") from error
    if not result.startswith(PNG):
        raise ValueError("渲染器未返回 PNG")
    return result


def normalize(payload):
    if (len(payload) < 33 or payload[:16] != PNG + b"\x00\x00\x00\x0dIHDR"):
        raise ValueError("请上传 PNG 图片")
    width, height = struct.unpack(">II", payload[16:24])
    if not 0 < width <= 4096 or not 0 < height <= 4096 or width * height > 12000000:
        raise ValueError("PNG 每边最多 4096 像素，总像素不超过 1200 万")
    return render("/usr/bin/convert", ["-limit", "thread", "1", "-limit", "memory", "96MiB", "-limit", "disk", "0",
                                       "png:-", "-strip", "-resize", "710x860>", "-background", "#121c2b",
                                       "-alpha", "remove", "-gravity", "center", "-extent", "768x960",
                                       "-depth", "8", "png24:-"], payload)


def generate(values):
    title = text(values.get("title"), "标题", 20)
    body = text(values.get("text", ""), "正文", 210, optional=True)
    metrics = values.get("metrics", [])
    if not isinstance(metrics, list) or len(metrics) > 6:
        raise ValueError("metrics 需要数组，最多 6 项")
    rows = []
    for item in metrics:
        if not isinstance(item, dict) or type(item.get("value")) not in (str, int, float):
            raise ValueError("指标需要 label 和文本或数值 value")
        rows.append((text(item.get("label"), "指标名", 12), text(str(item["value"]), "指标值", 14)))
    lines = [line[i:i + 20] for line in body.splitlines() for i in range(0, len(line), 20)]
    if len(lines) > 10:
        raise ValueError("正文折行后最多 10 行")
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="768" height="960">',
           '<rect width="768" height="960" fill="#121c2b"/>',
           '<rect x="28" y="28" width="712" height="904" rx="14" fill="#eee5d1"/>',
           '<path d="M63 70H705 M63 890H705" stroke="#bcac8d" stroke-width="2"/>',
           '<path d="M63 106V157" stroke="#a83b21" stroke-width="7"/>']

    def draw(x, y, size, color, content):
        svg.append('<text x="{}" y="{}" font-family="Noto Sans CJK SC" font-size="{}" fill="{}">{}</text>'.format(
            x, y, size, color, escape(content)))

    draw(82, 145, 30, "#232b26", title)
    y = 218
    for line in lines:
        draw(64, y, 29, "#232b26", line)
        y += 34
    y += 45
    for label, value in rows:
        draw(64, y, 27, "#232b26", label)
        draw(420, y, 20, "#a83b21", value)
        y += 45
    svg.append("</svg>")
    return render("/usr/bin/rsvg-convert", [], "".join(svg).encode("utf-8"))
