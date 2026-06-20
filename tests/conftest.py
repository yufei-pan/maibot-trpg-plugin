import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT.parent / "maibot-plugin-sdk"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)
