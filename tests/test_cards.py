import base64
import io
import re

from trpg_cards import build_card_html, to_compact_webp
from trpg_schema import blank_sheet, resolve_schema

TEMPLATE = "<h1>{{name}}</h1><img src='{{mugshot}}'><table>{{stats_rows}}</table>"


def test_build_card_html_fills_all_placeholders():
    schema = resolve_schema(None)
    sheet = blank_sheet(schema)
    sheet["name"] = "罗德"
    html = build_card_html(TEMPLATE, sheet=sheet, schema=schema, mugshot_uri="data:image/png;base64,AAA")
    assert "罗德" in html
    assert "data:image/png;base64,AAA" in html
    assert "力量" in html  # a stat label rendered
    assert not re.search(r"{{.*?}}", html)  # no leftover placeholders


def test_to_compact_webp_reencodes_smaller():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (400, 600), (255, 255, 255)).save(buf, format="PNG")
    png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    out = to_compact_webp(png_b64)
    assert isinstance(out, str) and out
    assert len(base64.b64decode(out)) <= len(buf.getvalue())
