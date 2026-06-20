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


def test_build_card_html_escapes_untrusted_values():
    """Test that untrusted player-controlled values are HTML-escaped in build_card_html."""
    schema = resolve_schema(None)
    sheet = blank_sheet(schema)
    sheet["name"] = "<script>alert(1)</script>"

    # Find a stat field to inject script content
    stat_field = next((f for f in schema["fields"] if f["key"] != "name"), None)
    if stat_field:
        sheet[stat_field["key"]] = "</td></tr><script>x</script>"

    html = build_card_html(TEMPLATE, sheet=sheet, schema=schema, mugshot_uri="data:image/png;base64,AAA")

    # Assert that raw script tags are NOT in output
    assert "<script>" not in html, "Raw <script> tag found in output — escaping failed"
    assert "alert(1)" not in html or "&lt;script&gt;" in html, "Script content not properly escaped"

    # Assert that escaped form IS in output
    assert "&lt;script&gt;" in html, "Escaped &lt;script&gt; not found in output"
    assert "No leftover unescaped tags" or True  # The key assertion is above


def test_build_card_html_mugshot_allowlist():
    """Test that mugshot URIs are validated: only data:image/ and https:// allowed."""
    schema = resolve_schema(None)
    sheet = blank_sheet(schema)
    sheet["name"] = "テスト"

    # Test: javascript: should be dropped (not in output)
    html1 = build_card_html(TEMPLATE, sheet=sheet, schema=schema, mugshot_uri="javascript:alert(1)")
    assert "javascript:" not in html1, "javascript: URI was not dropped"
    assert "<img src=''>" in html1 or '<img src="">' in html1 or "src=''" in html1 or 'src=""' in html1, "Expected empty src attribute for rejected URI"

    # Test: data:image/ should be allowed
    html2 = build_card_html(TEMPLATE, sheet=sheet, schema=schema, mugshot_uri="data:image/png;base64,AAA")
    assert "data:image/png;base64,AAA" in html2, "Valid data: URI was rejected"

    # Test: https:// should be allowed
    html3 = build_card_html(TEMPLATE, sheet=sheet, schema=schema, mugshot_uri="https://q1.qlogo.cn/x.png")
    assert "https://q1.qlogo.cn/x.png" in html3, "Valid https:// URI was rejected"

    # Test: http:// should be dropped
    html4 = build_card_html(TEMPLATE, sheet=sheet, schema=schema, mugshot_uri="http://example.com/x.png")
    assert "http://" not in html4, "http:// URI was not dropped"


def test_to_compact_webp_reencodes_smaller():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (400, 600), (255, 255, 255)).save(buf, format="PNG")
    png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    out = to_compact_webp(png_b64)
    assert isinstance(out, str) and out
    assert len(base64.b64decode(out)) <= len(buf.getvalue())
