import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_declared_capabilities_cover_ctx_usage():
    src = (ROOT / "plugin.py").read_text(encoding="utf-8")
    used = set(re.findall(r"self\.ctx\.([a-z_]+)", src))
    used.discard("logger")  # logger is always available, not a declared capability
    caps = json.loads((ROOT / "_manifest.json").read_text(encoding="utf-8"))["capabilities"]
    families = {c.split(".")[0] for c in caps}  # dotted method-level -> family, e.g. send.text -> send
    undeclared = used - families
    assert not undeclared, f"plugin.py uses undeclared capability families: {undeclared}"
    unused = families - used
    assert not unused, f"manifest declares unused capability families: {unused}"
