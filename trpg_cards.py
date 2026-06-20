"""角色卡渲染：HTML 占位符填充 + 把 Host 渲染的 PNG 无损重编码为 WebP（控制聊天图片体积）。"""

from __future__ import annotations

import base64
import html
import io
from typing import Any


def build_card_html(template: str, *, sheet: dict, schema: dict, mugshot_uri: str) -> str:
    rows: list[str] = []
    for f in schema.get("fields", []):
        if f["key"] == "name":
            continue
        val = sheet.get(f["key"], f.get("default"))
        if isinstance(val, list):
            val = "、".join(html.escape(str(x), quote=True) for x in val) if val else "—"
        else:
            val = html.escape(str(val), quote=True)
        label = html.escape(str(f.get("label", f["key"])), quote=True)
        rows.append(f"<tr><td class='k'>{label}</td><td>{val}</td></tr>")

    # Escape name
    name = html.escape(str(sheet.get("name", "")), quote=True)
    result = template.replace("{{name}}", name)

    # Validate and escape mugshot URI: allow only data: URLs (base64 images) or https:// URLs
    safe_mugshot = ""
    if mugshot_uri:
        stripped_uri = mugshot_uri.strip()
        if stripped_uri.lower().startswith("data:image/") or stripped_uri.lower().startswith("https://"):
            safe_mugshot = html.escape(stripped_uri, quote=True)
    result = result.replace("{{mugshot}}", safe_mugshot)

    result = result.replace("{{stats_rows}}", "".join(rows))
    return result


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
