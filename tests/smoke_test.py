import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Setup sys.path for direct python runs (conftest.py handles pytest)
import sys
for p in (ROOT, ROOT.parent / "maibot-plugin-sdk"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


def test_create_plugin_returns_instance():
    import plugin
    inst = plugin.create_plugin()
    assert inst.__class__.__name__ == "MaiTRPGPlugin"


def test_manifest_parses_and_declares_id():
    data = json.loads((ROOT / "_manifest.json").read_text(encoding="utf-8"))
    assert data["id"]
    assert "Yufei Pan" in json.dumps(data, ensure_ascii=False)  # robust to author being str or object


if __name__ == "__main__":
    test_create_plugin_returns_instance()
    test_manifest_parses_and_declares_id()
    print("OK")
