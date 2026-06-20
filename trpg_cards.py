"""角色卡渲染：HTML 占位符填充 + 把 Host 渲染的 PNG 无损重编码为 WebP（控制聊天图片体积）。"""

from __future__ import annotations

import base64
import io
from typing import Any


def build_card_html(template: str, *, sheet: dict, schema: dict, mugshot_uri: str) -> str:
    rows: list[str] = []
    for f in schema.get("fields", []):
        if f["key"] == "name":
            continue
        val = sheet.get(f["key"], f.get("default"))
        if isinstance(val, list):
            val = "、".join(str(x) for x in val) if val else "—"
        rows.append(f"<tr><td class='k'>{f.get('label', f['key'])}</td><td>{val}</td></tr>")
    html = template.replace("{{name}}", str(sheet.get("name", "")))
    html = html.replace("{{mugshot}}", mugshot_uri or "")
    html = html.replace("{{stats_rows}}", "".join(rows))
    return html


def to_compact_webp(png_b64: str, logger: Any = None) -> str:
    """把 PNG 无损重编码为 WebP；仅当更小才替换。移植自 maibook plugin.py:2079-2103。"""
    raw = base64.b64decode(png_b64)
    try:
        from PIL import Image
    except Exception as exc:  # noqa: BLE001
        if logger:
            logger.warning("麦麦跑团：未能加载 Pillow，图片按原始 PNG 发送：%s", exc)
        return png_b64
    try:
        with Image.open(io.BytesIO(raw)) as im:
            buf = io.BytesIO()
            im.save(buf, format="WEBP", lossless=True, method=6)
            webp = buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        if logger:
            logger.warning("麦麦跑团：WebP 压缩失败，按原始 PNG 发送：%s", exc)
        return png_b64
    if len(webp) < len(raw):
        return base64.b64encode(webp).decode("ascii")
    return png_b64
