# 麦麦跑团 / MaiTRPG — Phase 1 (Core Play Loop) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a playable group-chat TRPG plugin where a deterministic Python engine referees (dice, stats, ready gate, batch loop), a separate GM agent narrates, and MaiBot plays as an ordinary player.

**Architecture:** New first-party plugin repo `maibot-trpg-plugin/`. Complex logic lives in small prefixed top-level modules (`trpg_*.py`) imported absolutely (`from trpg_dice import ...`) so the same import works under the Host loader (it puts the plugin dir on `sys.path` and sets `submodule_search_locations`) and the offline `import plugin` smoke test. `plugin.py` is thin SDK glue: config model, lifecycle, `@Tool`/`@Command`/`@EventHandler` components, per-stream debounce timers, and the flush pipeline. Per chat stream, a session is a directory tree of TOML + Markdown + append-only logs.

**Tech Stack:** Python ≥3.10, `maibot-plugin-sdk` (`import maibot_sdk`), `tomllib` (read) + `tomli-w` (write), `Pillow` (WebP re-encode), `pytest`. Host capabilities via `self.ctx.*`: `send`, `db`, `llm`, `render`, `maisaka`, `person`, `config`, `logger`.

## Global Constraints

- **Language: Simplified Chinese first** — comments, log messages, tool/command descriptions, WebUI text, and the default GM prompt are zh-CN.
- **No silent fallbacks (不要兜底).** Surface errors completely; reject empty tool input with a real error message, never silent success (workspace memory: `plugin-tool-defensive-input`).
- **Tool naming:** functional prefixes, **≤4 tools per prefix**, distinct leading tokens, so a `tool_search` prefix query (top-5 cap) returns the whole category (workspace memory: `plugin-tool-search-5-result-cap`). Phase-1 prefixes: `session_`, `bible_`, `sheet_`.
- **Each `@Tool` brief_description starts with** `【麦麦跑团/MaiTRPG·<类>】` so MaiBot recognizes them in deferred-tool prompts.
- **Defensive tool input:** accept alias keys (e.g. `session`/`session_id`/`name`); reject empty required content.
- **Chat images small:** render at 1x, re-encode lossless WebP via Pillow before sending (workspace memory: `plugin-send-capability-return-contract`).
- **Authoritative dice:** the GM agent may *request* rolls but never produces the numbers; the Python engine rolls and the result is injected.
- **Imports:** `from ... import` before plain `import`, each alphabetized; stdlib/third-party before local. Local `trpg_*` modules imported absolutely.
- **`config_version` = `"1.0.0"`** this phase; `on_config_update` mirrors maibook's structure so future migrations slot in.

**Reuse anchors (copy verbatim where noted, with attribution comment):**
- `maibook-plugin/plugin.py:124-135` — `_safe_component` / `_safe_stream_dir`.
- `maibook-plugin/plugin.py:2079-2103` — `_to_compact_webp` (PNG→lossless WebP).
- `maibook-plugin/plugin.py:472-491` — maisaka `context.append` + `proactive.trigger`.
- `maibook-plugin/plugin.py:272-337,2268-2270` — config-section / `config_model` / `create_plugin` shape; import line for `Tool, ToolParameterInfo, ToolParamType` and (add) `EventHandler`, plus `from maibot_sdk.types import EventType`.
- `maibook-plugin/plugin.py:1271-1306,2252-2265` — `@Tool` / `@Command` shapes; `_resolve_stream_id(kwargs)`; tools return `dict` (`success`/`content`), commands reply via `ctx.send.text(text, stream_id)`.
- `maibot-impression-card-plugin/plugin.py:401-420` — `_render_card_text_template` placeholder fill; `tests/smoke_test.py::test_manifest_capabilities_cover_usage` — capability-vs-usage test to mirror.

---

### Task 0: Scaffold the plugin repo

**Files:**
- Create: `maibot-trpg-plugin/_manifest.json`
- Create: `maibot-trpg-plugin/config.default.toml`
- Create: `maibot-trpg-plugin/config.toml` (copy of default)
- Create: `maibot-trpg-plugin/.gitignore`
- Create: `maibot-trpg-plugin/plugin.py` (skeleton)
- Create: `maibot-trpg-plugin/tests/smoke_test.py`
- Create: `maibot-trpg-plugin/tests/conftest.py`

**Interfaces:**
- Produces: `create_plugin() -> MaiTRPGPlugin`; module `plugin` importable with the plugin dir + `../maibot-plugin-sdk` on `sys.path`.

- [ ] **Step 1: Write the failing test** — `tests/smoke_test.py`

```python
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
```

- [ ] **Step 2: Add `tests/conftest.py`** (puts plugin dir + sibling SDK on path for both pytest and direct run)

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT.parent / "maibot-plugin-sdk"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)
```

For direct `python tests/smoke_test.py` runs, replicate the same `sys.path` insertion at the top of `smoke_test.py` (conftest only loads under pytest).

> **Test environment deps:** from Task 1 on, the modules import `tomli_w` and (lazily) `PIL`. The runner must have them installed. Either `pip install tomli-w pillow pytest` once, or run tests via uv like maibook: `uv run --with tomli-w --with pillow --with-editable ../maibot-plugin-sdk pytest -v`. The per-task `PYTHONPATH=.:../maibot-plugin-sdk pytest …` commands assume those three are already importable.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk python tests/smoke_test.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'plugin'`.

- [ ] **Step 4: Write `_manifest.json`**

```json
{
  "manifest_version": 2,
  "id": "com.0-hz.maitrpg",
  "version": "0.1.0",
  "name": "麦麦跑团 (MaiTRPG)",
  "description": "让麦麦在群聊里主持并参与一场跑团（TRPG）：内部引擎做规则裁判（骰子/属性/就绪门禁/批处理回合），独立 GM 智能体负责叙事，麦麦作为普通玩家参与。每个聊天流一个会话目录（session.toml + bible/ + characters/ + world_state.md + 追加日志）。",
  "author": { "name": "Yufei Pan", "url": "https://github.com/yufei-pan" },
  "license": "MIT",
  "urls": {
    "repository": "https://github.com/yufei-pan/maibot-trpg-plugin",
    "homepage": "https://github.com/yufei-pan/maibot-trpg-plugin",
    "documentation": "https://github.com/yufei-pan/maibot-trpg-plugin/blob/main/README.md",
    "issues": "https://github.com/yufei-pan/maibot-trpg-plugin/issues"
  },
  "host_application": { "min_version": "1.0.0", "max_version": "1.99.99" },
  "sdk": { "min_version": "2.5.1", "max_version": "2.99.99" },
  "dependencies": [
    { "type": "python_package", "name": "tomli", "version_spec": ">=2.0.0" },
    { "type": "python_package", "name": "tomli-w", "version_spec": ">=1.0.0" },
    { "type": "python_package", "name": "Pillow", "version_spec": ">=10.0.0" }
  ],
  "capabilities": [
    "llm.generate",
    "send.text",
    "send.image",
    "render.html2png",
    "maisaka.context.append",
    "maisaka.proactive.trigger"
  ],
  "i18n": { "default_locale": "zh-CN" }
}
```

> This mirrors `maibook-plugin/_manifest.json` / `maibot-impression-card-plugin/_manifest.json` exactly: `manifest_version: 2`, **dotted method-level capabilities**, **dependency objects** (`{type, name, version_spec}`), bounded `host_application`/`sdk` ranges, and `i18n.default_locale`. Phase 1 only needs the six capabilities above (session storage is plain filesystem under `data/`, like maibook — no `database.*`/`config.get`; `self.config` reads injected config, not `ctx.config`). Phase 2 adds `database.*`/`person.*`/`knowledge.search` when recall/ingestion land. `tomli` is declared so reads work on Python 3.10 (stdlib `tomllib` is 3.11+).

- [ ] **Step 5: Write `config.default.toml`** (minimal; expanded in Task 9)

```toml
[plugin]
enabled = true
config_version = "1.0.0"
maibot_plays = true
```

Copy it to `config.toml`. Write `.gitignore`:

```
config.local.toml
data/
__pycache__/
.ruff_cache/
*.pyc
```

- [ ] **Step 6: Write `plugin.py` skeleton**

```python
"""麦麦跑团 / MaiTRPG 插件主体。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maibot_sdk import Field, MaiBotPlugin, PluginConfigBase

CURRENT_CONFIG_VERSION = "1.0.0"


class PluginSection(PluginConfigBase):
    __ui_label__ = "基础设置"

    enabled: bool = Field(default=True, description="是否启用插件")
    config_version: str = Field(default=CURRENT_CONFIG_VERSION, description="配置版本号")
    maibot_plays: bool = Field(default=True, description="开局时麦麦是否作为玩家自动加入")


class MaiTRPGConfig(PluginConfigBase):
    plugin: PluginSection = Field(default_factory=PluginSection)


class MaiTRPGPlugin(MaiBotPlugin):
    """麦麦跑团插件主体。"""

    config_model = MaiTRPGConfig

    def __init__(self) -> None:
        super().__init__()
        self._plugin_dir = Path(__file__).resolve().parent

    async def on_load(self) -> None:
        self.ctx.logger.info("麦麦跑团插件已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("麦麦跑团插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        if scope == "self":
            self.ctx.logger.info("麦麦跑团配置已更新: version=%s", version)


def create_plugin() -> MaiTRPGPlugin:
    return MaiTRPGPlugin()
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk python tests/smoke_test.py`
Expected: prints `OK`.

- [ ] **Step 8: Commit**

```bash
cd maibot-trpg-plugin && git init -q && git add -A
git commit -m "feat: scaffold maibot-trpg-plugin (manifest, config, skeleton, smoke test)"
```

---

### Task 1: Storage paths & files (`trpg_storage.py`)

**Files:**
- Create: `maibot-trpg-plugin/trpg_storage.py`
- Test: `maibot-trpg-plugin/tests/test_storage.py`

**Interfaces:**
- Produces:
  - `safe_stream_dir(stream_id: str) -> str`, `safe_component(value: str) -> str`
  - `class Paths` with `__init__(self, data_root: Path, stream_id: str, session_id: str)` and properties `session_dir`, `session_toml`, `state_toml`, `world_state`, `audit_log`, `bible_dir`, `characters_dir`, `episodes_dir`; methods `bible_file(name)`, `character_toml(member)`, `episode_log(n)`.
  - `read_toml(path: Path) -> dict`, `write_toml(path: Path, data: dict) -> None` (atomic: write tmp + `os.replace`).
  - `append_line(path: Path, line: str) -> None` (creates parents, appends `line + "\n"`).
  - `list_sessions(data_root: Path, stream_id: str) -> list[dict]` (reads each `session.toml`: returns `{"session_id", "status", "members", "title"}`).

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from trpg_storage import Paths, append_line, list_sessions, read_toml, safe_stream_dir, write_toml


def test_safe_stream_dir_sanitizes_and_is_stable():
    assert safe_stream_dir("group/123") == "group_123"
    assert safe_stream_dir("") .startswith("s_")
    assert safe_stream_dir("group:1") == safe_stream_dir("group:1")


def test_paths_layout(tmp_path):
    p = Paths(tmp_path, "g1", "camp1")
    assert p.session_dir == tmp_path / "g1" / "camp1"
    assert p.bible_file("world.md") == tmp_path / "g1" / "camp1" / "bible" / "world.md"
    assert p.character_toml("u9") == tmp_path / "g1" / "camp1" / "characters" / "u9.toml"


def test_toml_roundtrip_atomic(tmp_path):
    p = tmp_path / "x.toml"
    write_toml(p, {"status": "setup", "members": ["a", "b"]})
    assert read_toml(p) == {"status": "setup", "members": ["a", "b"]}
    assert read_toml(tmp_path / "missing.toml") == {}


def test_append_line_and_list_sessions(tmp_path):
    p = Paths(tmp_path, "g1", "camp1")
    append_line(p.audit_log, "roll u1 d20=14")
    assert p.audit_log.read_text(encoding="utf-8") == "roll u1 d20=14\n"
    write_toml(p.session_toml, {"session_id": "camp1", "status": "setup", "members": [], "title": "无标题"})
    sessions = list_sessions(tmp_path, "g1")
    assert sessions == [{"session_id": "camp1", "status": "setup", "members": [], "title": "无标题"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_storage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trpg_storage'`.

- [ ] **Step 3: Write `trpg_storage.py`**

```python
"""跑团存储：每个聊天流一个会话目录树，TOML + Markdown + 追加日志。"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10：标准库无 tomllib，回退到 tomli
    import tomli as tomllib

import tomli_w


def safe_component(value: str) -> str:
    """把任意字符串清洗为安全的单段文件/目录名（同 maibook plugin.py:124-127）。"""
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value).strip())
    return sanitized.strip(". ")


def safe_stream_dir(stream_id: str) -> str:
    """把 stream_id 映射为安全且稳定的目录名（同 maibook plugin.py:130-135）。"""
    safe = safe_component(stream_id)
    if safe:
        return safe
    return "s_" + hashlib.sha256(str(stream_id).encode("utf-8")).hexdigest()[:16]


class Paths:
    """单个会话目录的全部路径。"""

    def __init__(self, data_root: Path, stream_id: str, session_id: str) -> None:
        self.session_dir = Path(data_root) / safe_stream_dir(stream_id) / safe_component(session_id)

    @property
    def session_toml(self) -> Path:
        return self.session_dir / "session.toml"

    @property
    def state_toml(self) -> Path:
        return self.session_dir / "state.toml"

    @property
    def world_state(self) -> Path:
        return self.session_dir / "world_state.md"

    @property
    def audit_log(self) -> Path:
        return self.session_dir / "audit.log"

    @property
    def bible_dir(self) -> Path:
        return self.session_dir / "bible"

    @property
    def characters_dir(self) -> Path:
        return self.session_dir / "characters"

    @property
    def episodes_dir(self) -> Path:
        return self.session_dir / "episodes"

    def bible_file(self, name: str) -> Path:
        return self.bible_dir / safe_component(name)

    def character_toml(self, member: str) -> Path:
        return self.characters_dir / f"{safe_component(member)}.toml"

    def episode_log(self, n: int) -> Path:
        return self.episodes_dir / f"{int(n):02d}.log"


def read_toml(path: Path) -> dict[str, Any]:
    if not Path(path).exists():
        return {}
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def write_toml(path: Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        tomli_w.dump(data, fh)
    os.replace(tmp, path)


def append_line(path: Path, line: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line.rstrip("\n") + "\n")


def list_sessions(data_root: Path, stream_id: str) -> list[dict[str, Any]]:
    base = Path(data_root) / safe_stream_dir(stream_id)
    out: list[dict[str, Any]] = []
    if not base.exists():
        return out
    for child in sorted(base.iterdir()):
        meta = read_toml(child / "session.toml")
        if not meta:
            continue
        out.append({
            "session_id": meta.get("session_id", child.name),
            "status": meta.get("status", "setup"),
            "members": meta.get("members", []),
            "title": meta.get("title", "无标题"),
        })
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_storage.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add trpg_storage.py tests/test_storage.py
git commit -m "feat: storage paths, atomic TOML, append logs, session listing"
```

---

### Task 2: Dice engine (`trpg_dice.py`)

**Files:**
- Create: `maibot-trpg-plugin/trpg_dice.py`
- Test: `maibot-trpg-plugin/tests/test_dice.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Roll(expr: str, rolls: list[int], modifier: int, total: int)`
  - `@dataclass(frozen=True) class Check(d20: int, modifier: int, dc: int, total: int, success: bool, margin: int, crit: str)` where `crit ∈ {"none","success","fail"}`.
  - `roll(expr: str, *, rng: random.Random) -> Roll` — parses `NdM(+/-K)?` (e.g. `2d6+3`, `d20`, `4d8-1`).
  - `check(modifier: int, dc: int, *, rng: random.Random, advantage: int = 0) -> Check` — `advantage` is `+1` (roll 2 keep high), `-1` (keep low), `0` (single d20); nat-20 → `crit="success"`, nat-1 → `crit="fail"`.

- [ ] **Step 1: Write the failing test**

```python
import random

from trpg_dice import Check, Roll, check, roll


def test_roll_is_deterministic_with_seed():
    a = roll("2d6+3", rng=random.Random(42))
    b = roll("2d6+3", rng=random.Random(42))
    assert a == b
    assert a.modifier == 3
    assert a.total == sum(a.rolls) + 3
    assert len(a.rolls) == 2
    assert all(1 <= r <= 6 for r in a.rolls)


def test_roll_single_die_and_negative_modifier():
    r = roll("d20", rng=random.Random(1))
    assert len(r.rolls) == 1 and 1 <= r.rolls[0] <= 20
    r2 = roll("4d8-1", rng=random.Random(1))
    assert r2.modifier == -1 and r2.total == sum(r2.rolls) - 1


def test_check_dc_compare_and_margin():
    c = check(5, 15, rng=random.Random(7))
    assert isinstance(c, Check)
    assert c.total == c.d20 + 5
    assert c.success == (c.total >= 15)
    assert c.margin == c.total - 15


def test_advantage_keeps_higher():
    # advantage must be >= a single-roll baseline under the same seed sequence
    adv = check(0, 10, rng=random.Random(3), advantage=1)
    dis = check(0, 10, rng=random.Random(3), advantage=-1)
    assert adv.d20 >= dis.d20


def test_natural_crit_flags():
    # find a seed producing a natural 20 and natural 1
    nat20 = next(s for s in range(1000) if check(0, 99, rng=random.Random(s)).d20 == 20)
    assert check(0, 99, rng=random.Random(nat20)).crit == "success"
    nat1 = next(s for s in range(1000) if check(0, 0, rng=random.Random(s)).d20 == 1)
    assert check(0, 0, rng=random.Random(nat1)).crit == "fail"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_dice.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trpg_dice'`.

- [ ] **Step 3: Write `trpg_dice.py`**

```python
"""权威骰子引擎：纯 Python，可注入 RNG 以保证可测试与可复现。GM 只能请求掷骰，不能伪造结果。"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

_DICE_RE = re.compile(r"^\s*(\d*)d(\d+)\s*([+-]\s*\d+)?\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Roll:
    expr: str
    rolls: list[int]
    modifier: int
    total: int


@dataclass(frozen=True)
class Check:
    d20: int
    modifier: int
    dc: int
    total: int
    success: bool
    margin: int
    crit: str  # none | success | fail


def roll(expr: str, *, rng: random.Random) -> Roll:
    m = _DICE_RE.match(str(expr))
    if not m:
        raise ValueError(f"无法解析骰子表达式：{expr!r}（应形如 2d6+3 / d20 / 4d8-1）")
    count = int(m.group(1)) if m.group(1) else 1
    sides = int(m.group(2))
    if count < 1 or sides < 2:
        raise ValueError(f"骰子参数非法：{expr!r}")
    modifier = int(m.group(3).replace(" ", "")) if m.group(3) else 0
    rolls = [rng.randint(1, sides) for _ in range(count)]
    return Roll(expr=str(expr).strip(), rolls=rolls, modifier=modifier, total=sum(rolls) + modifier)


def check(modifier: int, dc: int, *, rng: random.Random, advantage: int = 0) -> Check:
    a = rng.randint(1, 20)
    if advantage > 0:
        b = rng.randint(1, 20)
        d20 = max(a, b)
    elif advantage < 0:
        b = rng.randint(1, 20)
        d20 = min(a, b)
    else:
        d20 = a
    total = d20 + modifier
    crit = "success" if d20 == 20 else "fail" if d20 == 1 else "none"
    return Check(d20=d20, modifier=modifier, dc=dc, total=total,
                 success=total >= dc, margin=total - dc, crit=crit)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_dice.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add trpg_dice.py tests/test_dice.py
git commit -m "feat: authoritative seedable dice engine (roll + d20 check w/ advantage & crits)"
```

---

### Task 3: Stat schema (`trpg_schema.py`)

**Files:**
- Create: `maibot-trpg-plugin/trpg_schema.py`
- Test: `maibot-trpg-plugin/tests/test_schema.py`

**Interfaces:**
- Produces:
  - `DEFAULT_SCHEMA: dict` — `{"fields": [{"key","label","type","default","required"}, ...]}` with a system-agnostic block: `name`(str,required), `level`(int,1), `hp`(int,10,required), `ac`(int,10), six attrs `str_/dex/con/int_/wis/cha`(int,10), `inventory`(list,[]), `conditions`(list,[]), `notes`(str,"").
  - `resolve_schema(custom: dict | None) -> dict` — `None`/empty → copy of `DEFAULT_SCHEMA`; else the custom dict (validated to have non-empty `fields` each with `key`+`type`).
  - `apply_edits(schema: dict, *, add: list[dict] = (), modify: list[dict] = (), remove: list[str] = ()) -> dict` — semi-custom: append new fields, patch existing by `key`, drop by `key`. Returns a new dict.
  - `field_types(schema) -> dict[str,str]`.
  - `validate_sheet(sheet: dict, schema: dict) -> list[str]` — list of human-readable problems (missing required field, wrong type).
  - `sheet_complete(sheet: dict, schema: dict) -> bool` — `validate_sheet == []`.
  - `blank_sheet(schema: dict) -> dict` — every field set to its `default`.

- [ ] **Step 1: Write the failing test**

```python
from trpg_schema import (DEFAULT_SCHEMA, apply_edits, blank_sheet, resolve_schema,
                         sheet_complete, validate_sheet)


def test_resolve_default_when_none():
    s = resolve_schema(None)
    keys = {f["key"] for f in s["fields"]}
    assert {"name", "hp", "ac", "str_", "inventory"} <= keys
    s["fields"].append({"key": "x"})
    assert len(resolve_schema(None)["fields"]) == len(DEFAULT_SCHEMA["fields"])  # no shared mutation


def test_semi_custom_add_modify_remove():
    s = apply_edits(resolve_schema(None),
                    add=[{"key": "sanity", "label": "理智", "type": "int", "default": 100, "required": True}],
                    modify=[{"key": "hp", "default": 20}],
                    remove=["cha"])
    by = {f["key"]: f for f in s["fields"]}
    assert by["sanity"]["default"] == 100
    assert by["hp"]["default"] == 20
    assert "cha" not in by


def test_fully_custom_replace():
    custom = {"fields": [{"key": "grit", "label": "胆识", "type": "int", "default": 3, "required": True}]}
    assert resolve_schema(custom) == custom


def test_validate_and_complete():
    s = resolve_schema(None)
    blank = blank_sheet(s)
    # blank has name="" -> required name missing
    problems = validate_sheet(blank, s)
    assert any("name" in p for p in problems)
    blank["name"] = "阿强"
    assert sheet_complete(blank, s)
    blank["hp"] = "ten"  # wrong type
    assert not sheet_complete(blank, s)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trpg_schema'`.

- [ ] **Step 3: Write `trpg_schema.py`**

```python
"""属性表 schema：支持默认 / 半自定义（增删改字段）/ 全自定义。系统无关、强类型。"""

from __future__ import annotations

import copy
from typing import Any

_PY_TYPES = {"str": str, "int": int, "float": (int, float), "bool": bool, "list": list}

DEFAULT_SCHEMA: dict[str, Any] = {
    "fields": [
        {"key": "name", "label": "姓名", "type": "str", "default": "", "required": True},
        {"key": "level", "label": "等级", "type": "int", "default": 1, "required": False},
        {"key": "hp", "label": "生命值", "type": "int", "default": 10, "required": True},
        {"key": "ac", "label": "护甲", "type": "int", "default": 10, "required": False},
        {"key": "str_", "label": "力量", "type": "int", "default": 10, "required": False},
        {"key": "dex", "label": "敏捷", "type": "int", "default": 10, "required": False},
        {"key": "con", "label": "体质", "type": "int", "default": 10, "required": False},
        {"key": "int_", "label": "智力", "type": "int", "default": 10, "required": False},
        {"key": "wis", "label": "感知", "type": "int", "default": 10, "required": False},
        {"key": "cha", "label": "魅力", "type": "int", "default": 10, "required": False},
        {"key": "inventory", "label": "物品", "type": "list", "default": [], "required": False},
        {"key": "conditions", "label": "状态", "type": "list", "default": [], "required": False},
        {"key": "notes", "label": "备注", "type": "str", "default": "", "required": False},
    ]
}


def resolve_schema(custom: dict[str, Any] | None) -> dict[str, Any]:
    if not custom or not custom.get("fields"):
        return copy.deepcopy(DEFAULT_SCHEMA)
    for f in custom["fields"]:
        if not f.get("key") or f.get("type") not in _PY_TYPES:
            raise ValueError(f"自定义 schema 字段非法（需有 key 与合法 type）：{f!r}")
    return copy.deepcopy(custom)


def apply_edits(schema: dict[str, Any], *, add: list[dict] = (), modify: list[dict] = (),
                remove: list[str] = ()) -> dict[str, Any]:
    fields = [copy.deepcopy(f) for f in schema["fields"]]
    by_key = {f["key"]: f for f in fields}
    for patch in modify:
        key = patch.get("key")
        if key in by_key:
            by_key[key].update({k: v for k, v in patch.items() if k != "key"})
    rm = set(remove)
    fields = [f for f in fields if f["key"] not in rm]
    existing = {f["key"] for f in fields}
    for f in add:
        if f.get("key") and f["key"] not in existing:
            if f.get("type") not in _PY_TYPES:
                raise ValueError(f"新增字段 type 非法：{f!r}")
            fields.append(copy.deepcopy(f))
    return {"fields": fields}


def field_types(schema: dict[str, Any]) -> dict[str, str]:
    return {f["key"]: f["type"] for f in schema["fields"]}


def blank_sheet(schema: dict[str, Any]) -> dict[str, Any]:
    return {f["key"]: copy.deepcopy(f.get("default")) for f in schema["fields"]}


def validate_sheet(sheet: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for f in schema["fields"]:
        key, typ, label = f["key"], f["type"], f.get("label", f["key"])
        val = sheet.get(key, None)
        if f.get("required"):
            if val is None or (isinstance(val, str) and not val.strip()) or val == []:
                problems.append(f"缺少必填字段 {label}（{key}）")
                continue
        if val is not None and not isinstance(val, _PY_TYPES[typ]):
            problems.append(f"字段 {label}（{key}）类型应为 {typ}")
    return problems


def sheet_complete(sheet: dict[str, Any], schema: dict[str, Any]) -> bool:
    return validate_sheet(sheet, schema) == []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_schema.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add trpg_schema.py tests/test_schema.py
git commit -m "feat: stat schema (default/semi-custom/custom) + sheet validation"
```

---

### Task 4: Session model, membership & ready gate (`trpg_session.py`)

**Files:**
- Create: `maibot-trpg-plugin/trpg_session.py`
- Test: `maibot-trpg-plugin/tests/test_session.py`

**Interfaces:**
- Consumes: `trpg_schema.sheet_complete`.
- Produces:
  - Status constants `SETUP="setup"`, `READY="ready"`, `RUNNING="running"`, `STOPPED="stopped"`.
  - `@dataclass class ReadyReport(ok: bool, missing: list[str])`.
  - `new_session_meta(session_id: str, title: str, *, maibot_member: str | None) -> dict` — initial `session.toml` dict (`status=SETUP`, `members=[maibot_member?]`, `pending_cards=[...]`, `title`, `schema_custom=False`).
  - `add_member(meta: dict, member: str) -> dict`, `remove_member(meta, member)`, `mark_card_done(meta, member)`, `mark_card_pending(meta, member)` — pure, return new meta.
  - `ready_check(meta: dict, *, bible_present: dict[str,bool], schema: dict, sheets: dict[str,dict]) -> ReadyReport` — requires `bible_present["world"]`, `["plot"]`, `["gm_subprompt"]` all True; `schema` non-empty; every member has a `sheets[member]` that is `sheet_complete`.
  - `story_held(meta: dict) -> bool` — running session with any member in `pending_cards`.

- [ ] **Step 1: Write the failing test**

```python
from trpg_schema import blank_sheet, resolve_schema
from trpg_session import (READY, RUNNING, SETUP, add_member, mark_card_done, new_session_meta,
                          ready_check, story_held)


def _complete_sheet():
    s = resolve_schema(None)
    sheet = blank_sheet(s)
    sheet["name"] = "英雄"
    return s, sheet


def test_new_session_includes_maibot_member():
    meta = new_session_meta("camp1", "初章", maibot_member="mai")
    assert meta["status"] == SETUP and meta["members"] == ["mai"]


def test_ready_blocks_until_bible_and_cards_complete():
    schema, sheet = _complete_sheet()
    meta = add_member(new_session_meta("c", "t", maibot_member=None), "u1")
    present = {"world": True, "plot": False, "gm_subprompt": True}
    rep = ready_check(meta, bible_present=present, schema=schema, sheets={"u1": sheet})
    assert not rep.ok and any("plot" in m or "剧情" in m for m in rep.missing)

    present["plot"] = True
    rep2 = ready_check(meta, bible_present=present, schema=schema, sheets={"u1": {}})
    assert not rep2.ok and any("u1" in m for m in rep2.missing)

    rep3 = ready_check(meta, bible_present=present, schema=schema, sheets={"u1": sheet})
    assert rep3.ok and rep3.missing == []


def test_story_held_for_pending_card_in_running():
    meta = add_member(new_session_meta("c", "t", maibot_member=None), "u2")
    meta["status"] = RUNNING
    assert story_held(meta)            # u2 still pending
    meta = mark_card_done(meta, "u2")
    assert not story_held(meta)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trpg_session'`.

- [ ] **Step 3: Write `trpg_session.py`**

```python
"""会话模型：状态、成员、就绪门禁、新玩家挂起判定。纯函数，persistence 由 plugin.py 落盘。"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from trpg_schema import sheet_complete

SETUP = "setup"
READY = "ready"
RUNNING = "running"
STOPPED = "stopped"

_BIBLE_LABELS = {"world": "世界设定", "plot": "剧情/钩子", "gm_subprompt": "GM 子提示词"}


@dataclass
class ReadyReport:
    ok: bool
    missing: list[str] = field(default_factory=list)


def new_session_meta(session_id: str, title: str, *, maibot_member: str | None) -> dict[str, Any]:
    members = [maibot_member] if maibot_member else []
    return {
        "session_id": session_id,
        "title": title or "无标题",
        "status": SETUP,
        "members": list(members),
        "pending_cards": list(members),  # cards start incomplete
        "schema_custom": False,
    }


def add_member(meta: dict[str, Any], member: str) -> dict[str, Any]:
    meta = copy.deepcopy(meta)
    if member not in meta["members"]:
        meta["members"].append(member)
    if member not in meta["pending_cards"]:
        meta["pending_cards"].append(member)
    return meta


def remove_member(meta: dict[str, Any], member: str) -> dict[str, Any]:
    meta = copy.deepcopy(meta)
    meta["members"] = [m for m in meta["members"] if m != member]
    meta["pending_cards"] = [m for m in meta["pending_cards"] if m != member]
    return meta


def mark_card_done(meta: dict[str, Any], member: str) -> dict[str, Any]:
    meta = copy.deepcopy(meta)
    meta["pending_cards"] = [m for m in meta["pending_cards"] if m != member]
    return meta


def mark_card_pending(meta: dict[str, Any], member: str) -> dict[str, Any]:
    meta = copy.deepcopy(meta)
    if member in meta["members"] and member not in meta["pending_cards"]:
        meta["pending_cards"].append(member)
    return meta


def ready_check(meta: dict[str, Any], *, bible_present: dict[str, bool], schema: dict[str, Any],
                sheets: dict[str, dict]) -> ReadyReport:
    missing: list[str] = []
    for key, label in _BIBLE_LABELS.items():
        if not bible_present.get(key):
            missing.append(f"缺少{label}（{key}）")
    if not schema or not schema.get("fields"):
        missing.append("缺少属性 schema（stat_schema）")
    if not meta["members"]:
        missing.append("没有任何玩家加入")
    for member in meta["members"]:
        sheet = sheets.get(member) or {}
        if not schema or not sheet_complete(sheet, schema):
            missing.append(f"玩家 {member} 的角色卡未完成")
    return ReadyReport(ok=not missing, missing=missing)


def story_held(meta: dict[str, Any]) -> bool:
    return meta.get("status") == RUNNING and bool(meta.get("pending_cards"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_session.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add trpg_session.py tests/test_session.py
git commit -m "feat: session model, membership, ready gate, new-player hold"
```

---

### Task 5: Batch buffer & runaway guard (`trpg_batch.py`)

**Files:**
- Create: `maibot-trpg-plugin/trpg_batch.py`
- Test: `maibot-trpg-plugin/tests/test_batch.py`

**Interfaces:**
- Produces:
  - `is_ooc(text: str, marker: str) -> bool` — True if text starts with `marker` (e.g. `/ooc`) or is wrapped in `(( ))`.
  - `clean_action(text: str, marker: str) -> str` — strip a leading `marker`/`/do`/`/say` prefix, return the action text.
  - `@dataclass class Entry(author: str, kind: str, text: str)` where `kind ∈ {"human","maibot","system"}`.
  - `@dataclass class BatchBuffer` with `entries: list[Entry]`, methods `add(entry)`, `drain() -> list[Entry]` (returns & clears), `has_human() -> bool`.
  - `@dataclass class AdvanceDecision(advance: bool, reason: str)`.
  - `decide_advance(buffer: BatchBuffer, consecutive_auto: int, max_consecutive_auto: int) -> AdvanceDecision` — advance only if buffer has ≥1 human entry **or** `consecutive_auto < max_consecutive_auto` while non-empty; never advance an empty buffer.

- [ ] **Step 1: Write the failing test**

```python
from trpg_batch import (AdvanceDecision, BatchBuffer, Entry, clean_action, decide_advance,
                        is_ooc)


def test_ooc_detection():
    assert is_ooc("/ooc 等下我去倒水", "/ooc")
    assert is_ooc("(( brb ))", "/ooc")
    assert not is_ooc("我拔出长剑", "/ooc")


def test_clean_action_strips_prefix():
    assert clean_action("/do 撬锁", "/ooc") == "撬锁"
    assert clean_action("/say 站住！", "/ooc") == "站住！"
    assert clean_action("我环顾四周", "/ooc") == "我环顾四周"


def test_buffer_drain_and_has_human():
    b = BatchBuffer()
    b.add(Entry("mai", "maibot", "我点头"))
    assert not b.has_human()
    b.add(Entry("u1", "human", "我开门"))
    assert b.has_human()
    drained = b.drain()
    assert [e.author for e in drained] == ["mai", "u1"]
    assert b.entries == []


def test_runaway_guard():
    empty = BatchBuffer()
    assert decide_advance(empty, 0, 2).advance is False

    human = BatchBuffer(); human.add(Entry("u1", "human", "x"))
    assert decide_advance(human, 5, 2).advance is True  # human always advances

    only_mai = BatchBuffer(); only_mai.add(Entry("mai", "maibot", "x"))
    assert decide_advance(only_mai, 1, 2).advance is True   # under cap
    assert decide_advance(only_mai, 2, 2).advance is False  # cap reached, no human
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_batch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trpg_batch'`.

- [ ] **Step 3: Write `trpg_batch.py`**

```python
"""批处理缓冲与防失控守卫：把一段时间内的台面发言攒成一个 GM 回合。"""

from __future__ import annotations

from dataclasses import dataclass, field

_ACTION_PREFIXES = ("/do", "/say")


def is_ooc(text: str, marker: str) -> bool:
    t = str(text).strip()
    if marker and t.startswith(marker):
        return True
    return t.startswith("((") and t.endswith("))")


def clean_action(text: str, marker: str) -> str:
    t = str(text).strip()
    for pre in _ACTION_PREFIXES:
        if t.lower().startswith(pre):
            return t[len(pre):].strip()
    if marker and t.startswith(marker):
        return t[len(marker):].strip()
    return t


@dataclass
class Entry:
    author: str
    kind: str  # human | maibot | system
    text: str


@dataclass
class BatchBuffer:
    entries: list[Entry] = field(default_factory=list)

    def add(self, entry: Entry) -> None:
        self.entries.append(entry)

    def has_human(self) -> bool:
        return any(e.kind == "human" for e in self.entries)

    def drain(self) -> list[Entry]:
        out = list(self.entries)
        self.entries = []
        return out


@dataclass
class AdvanceDecision:
    advance: bool
    reason: str


def decide_advance(buffer: BatchBuffer, consecutive_auto: int, max_consecutive_auto: int) -> AdvanceDecision:
    if not buffer.entries:
        return AdvanceDecision(False, "缓冲为空")
    if buffer.has_human():
        return AdvanceDecision(True, "包含真人行动")
    if consecutive_auto < max_consecutive_auto:
        return AdvanceDecision(True, "未达连续自动推进上限")
    return AdvanceDecision(False, "已达连续自动推进上限且无真人行动")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_batch.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add trpg_batch.py tests/test_batch.py
git commit -m "feat: batch buffer, OOC filtering, runaway guard"
```

---

### Task 6: GM context assembly (`trpg_context.py`)

**Files:**
- Create: `maibot-trpg-plugin/trpg_context.py`
- Test: `maibot-trpg-plugin/tests/test_context.py`

**Interfaces:**
- Consumes: `trpg_batch.Entry`.
- Produces:
  - `bible_block(bible_texts: dict[str,str]) -> str` — concatenates non-empty bible sections under `## <name>` headers, stable key order.
  - `assemble_messages(*, world_state: str, recent_turns: list[Entry], batch: list[Entry], char_budget: int) -> list[dict]` — returns `[{role, content}]`. Role map: `human`/`maibot` → `"user"` (prefixed `「<author>」`), GM turns (`kind=="gm"`) → `"assistant"`, `system` → `"user"` prefixed `[系统]`. `world_state` is the first user message (`[当前局势] …`). When the total char count exceeds `char_budget`, drop oldest `recent_turns` first (never drop the current `batch` or `world_state`).

- [ ] **Step 1: Write the failing test**

```python
from trpg_batch import Entry
from trpg_context import assemble_messages, bible_block


def test_bible_block_orders_and_skips_empty():
    block = bible_block({"world": "高塔林立", "plot": "", "gm_subprompt": "严厉"})
    assert "## world" in block and "高塔林立" in block
    assert "## plot" not in block  # empty skipped


def test_role_mapping_and_world_state_first():
    msgs = assemble_messages(
        world_state="队伍在城门口",
        recent_turns=[Entry("u1", "human", "我敲门"), Entry("gm", "gm", "门开了")],
        batch=[Entry("mai", "maibot", "我跟上")],
        char_budget=10_000,
    )
    assert msgs[0]["role"] == "user" and "当前局势" in msgs[0]["content"]
    assert msgs[1] == {"role": "user", "content": "「u1」我敲门"}
    assert msgs[2] == {"role": "assistant", "content": "门开了"}
    assert msgs[-1] == {"role": "user", "content": "「mai」我跟上"}


def test_budget_drops_oldest_recent_but_keeps_batch():
    recent = [Entry(f"u{i}", "human", "X" * 100) for i in range(50)]
    batch = [Entry("u1", "human", "关键行动")]
    msgs = assemble_messages(world_state="W", recent_turns=recent, batch=batch, char_budget=500)
    joined = "".join(m["content"] for m in msgs)
    assert "关键行动" in joined          # batch preserved
    assert "当前局势" in msgs[0]["content"]  # world_state preserved
    assert len(joined) <= 500 + 200      # roughly within budget (allow prefixes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trpg_context'`.

- [ ] **Step 3: Write `trpg_context.py`**

```python
"""GM 上下文装配：bible 置顶（缓存友好）→ 当前局势 → 近期回合 → 本批次；按字符预算裁剪最旧回合。"""

from __future__ import annotations

from trpg_batch import Entry


def bible_block(bible_texts: dict[str, str]) -> str:
    parts: list[str] = []
    for key in sorted(bible_texts):
        text = (bible_texts.get(key) or "").strip()
        if text:
            parts.append(f"## {key}\n{text}")
    return "\n\n".join(parts)


def _to_message(entry: Entry) -> dict[str, str]:
    if entry.kind == "gm":
        return {"role": "assistant", "content": entry.text}
    if entry.kind == "system":
        return {"role": "user", "content": f"[系统] {entry.text}"}
    return {"role": "user", "content": f"「{entry.author}」{entry.text}"}


def assemble_messages(*, world_state: str, recent_turns: list[Entry], batch: list[Entry],
                      char_budget: int) -> list[dict]:
    head = {"role": "user", "content": f"[当前局势] {world_state}".strip()}
    tail = [_to_message(e) for e in batch]
    fixed_len = len(head["content"]) + sum(len(m["content"]) for m in tail)
    budget = max(0, int(char_budget) - fixed_len)

    middle: list[dict] = []
    for entry in reversed(recent_turns):  # newest first; keep until budget exhausted
        msg = _to_message(entry)
        if len(msg["content"]) > budget:
            break
        budget -= len(msg["content"])
        middle.append(msg)
    middle.reverse()
    return [head, *middle, *tail]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_context.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add trpg_context.py tests/test_context.py
git commit -m "feat: char-budgeted GM context assembly"
```

---

### Task 7: GM prompt build, roll-marker parsing & result formatting (`trpg_gm.py`)

**Files:**
- Create: `maibot-trpg-plugin/trpg_gm.py`
- Test: `maibot-trpg-plugin/tests/test_gm.py`

**Interfaces:**
- Consumes: `trpg_dice.Check`.
- Produces:
  - `build_system_prompt(main_gm_prompt: str, gm_subprompt: str, schema_summary: str) -> str`.
  - `schema_summary(schema: dict) -> str` — one-line list of `label(key)` for the GM.
  - `@dataclass class RollRequest(actor: str, modifier: int, dc: int, advantage: int, reason: str)`.
  - `parse_roll_requests(gm_text: str) -> list[RollRequest]` — parses fenced blocks:
    ```
    ===ROLL===
    actor: u1
    modifier: 3
    dc: 15
    advantage: 0
    reason: 撬锁
    ===END===
    ```
    Malformed/partial blocks are skipped (no exception).
  - `format_roll_result(req: RollRequest, result: Check) -> str` — a `[系统]`-ready zh-CN line.
  - `extract_world_state(gm_text: str) -> str | None` — content of a `===WORLD_STATE=== … ===END===` block, else None.
  - `strip_markers(gm_text: str) -> str` — narration with all `===…=== … ===END===` blocks removed, trimmed.

- [ ] **Step 1: Write the failing test**

```python
import random

from trpg_dice import check
from trpg_gm import (RollRequest, build_system_prompt, extract_world_state, format_roll_result,
                     parse_roll_requests, schema_summary, strip_markers)
from trpg_schema import resolve_schema

GM_TEXT = """你走到门前。
===ROLL===
actor: u1
modifier: 3
dc: 15
advantage: 1
reason: 撬锁
===END===
===WORLD_STATE===
队伍位于地牢入口，火把将尽。
===END===
门后传来脚步声。"""


def test_build_system_prompt_includes_parts():
    p = build_system_prompt("你是GM", "本场偏黑暗", "力量(str_)")
    assert "你是GM" in p and "本场偏黑暗" in p and "str_" in p


def test_schema_summary():
    assert "name" in schema_summary(resolve_schema(None))


def test_parse_roll_requests():
    reqs = parse_roll_requests(GM_TEXT)
    assert len(reqs) == 1
    assert reqs[0] == RollRequest(actor="u1", modifier=3, dc=15, advantage=1, reason="撬锁")


def test_parse_skips_malformed():
    assert parse_roll_requests("===ROLL===\nactor: u1\n===END===") == []  # missing dc/modifier


def test_format_roll_result_mentions_outcome():
    req = RollRequest("u1", 3, 15, 0, "撬锁")
    line = format_roll_result(req, check(3, 15, rng=random.Random(0)))
    assert "u1" in line and ("成功" in line or "失败" in line)


def test_extract_and_strip():
    assert "火把将尽" in extract_world_state(GM_TEXT)
    clean = strip_markers(GM_TEXT)
    assert "===ROLL===" not in clean and "actor: u1" not in clean
    assert "你走到门前" in clean and "门后传来脚步声" in clean
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_gm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trpg_gm'`.

- [ ] **Step 3: Write `trpg_gm.py`**

```python
"""GM 智能体的提示词构建与标记解析（纯文本处理；llm.generate 在 plugin.py 中调用）。
GM 通过 ===ROLL=== 区块请求掷骰，永不自行给出骰值；引擎掷骰后把结果作为 [系统] 回合注入。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from trpg_dice import Check

_BLOCK_RE = re.compile(r"===([A-Z_]+)===\s*\n(.*?)\n?===END===", re.DOTALL)


def schema_summary(schema: dict) -> str:
    return "、".join(f"{f.get('label', f['key'])}({f['key']})" for f in schema.get("fields", []))


def build_system_prompt(main_gm_prompt: str, gm_subprompt: str, schema_summary_text: str) -> str:
    return (
        f"{main_gm_prompt.strip()}\n\n"
        f"# 本场设定\n{gm_subprompt.strip()}\n\n"
        f"# 角色属性字段\n{schema_summary_text}\n\n"
        "# 掷骰协议\n需要任何检定/攻击时，输出一个区块（可多个），不要自己编造骰值：\n"
        "===ROLL===\nactor: <玩家ID>\nmodifier: <整数>\ndc: <整数>\nadvantage: <-1|0|1>\nreason: <简述>\n===END===\n"
        "若局势发生变化，用 ===WORLD_STATE=== <新的一句话局势> ===END=== 更新。"
    )


@dataclass
class RollRequest:
    actor: str
    modifier: int
    dc: int
    advantage: int
    reason: str


def _parse_kv(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in body.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def parse_roll_requests(gm_text: str) -> list[RollRequest]:
    reqs: list[RollRequest] = []
    for name, body in _BLOCK_RE.findall(gm_text):
        if name != "ROLL":
            continue
        kv = _parse_kv(body)
        try:
            reqs.append(RollRequest(
                actor=kv["actor"],
                modifier=int(kv["modifier"]),
                dc=int(kv["dc"]),
                advantage=int(kv.get("advantage", "0")),
                reason=kv.get("reason", ""),
            ))
        except (KeyError, ValueError):
            continue  # 跳过残缺/非法区块，不兜底也不抛断流程
    return reqs


def format_roll_result(req: RollRequest, result: Check) -> str:
    verdict = "成功" if result.success else "失败"
    crit = {"success": "（大成功！）", "fail": "（大失败！）", "none": ""}[result.crit]
    return (f"{req.actor} 进行「{req.reason or '检定'}」：d20={result.d20} "
            f"+{req.modifier} = {result.total} vs DC{req.dc} → {verdict}{crit}")


def extract_world_state(gm_text: str) -> str | None:
    for name, body in _BLOCK_RE.findall(gm_text):
        if name == "WORLD_STATE":
            return body.strip()
    return None


def strip_markers(gm_text: str) -> str:
    return _BLOCK_RE.sub("", gm_text).strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_gm.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add trpg_gm.py tests/test_gm.py
git commit -m "feat: GM prompt build + roll/world-state marker parsing + result formatting"
```

---

### Task 8: Character card render (`trpg_cards.py`)

**Files:**
- Create: `maibot-trpg-plugin/trpg_cards.py`
- Create: `maibot-trpg-plugin/assets/card.html`
- Test: `maibot-trpg-plugin/tests/test_cards.py`

**Interfaces:**
- Produces:
  - `build_card_html(template: str, *, sheet: dict, schema: dict, mugshot_uri: str) -> str` — replaces `{{name}}`, `{{mugshot}}`, and `{{stats_rows}}` (an HTML `<tr>` per schema field: `label` + value); leaves no `{{...}}` placeholder behind.
  - `to_compact_webp(png_b64: str, logger=None) -> str` — verbatim port of `maibook-plugin/plugin.py:2079-2103` (`_to_compact_webp`), as a module function taking an optional logger.

- [ ] **Step 1: Write the failing test**

```python
import base64
import io
import re

from trpg_cards import build_card_html, to_compact_webp
from trpg_schema import blank_sheet, resolve_schema

TEMPLATE = "<h1>{{name}}</h1><img src='{{mugshot}}'><table>{{stats_rows}}</table>"


def test_build_card_html_fills_all_placeholders():
    schema = resolve_schema(None)
    sheet = blank_sheet(schema); sheet["name"] = "罗德"
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_cards.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trpg_cards'`.

- [ ] **Step 3: Write `assets/card.html`** (minimal zh-CN template; placeholders `{{name}}`, `{{mugshot}}`, `{{stats_rows}}`)

```html
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
  body{margin:0;font-family:"Noto Sans SC",sans-serif;background:#1d1b16;color:#efe7d6;width:520px}
  .card{padding:24px}
  .head{display:flex;align-items:center;gap:16px}
  .head img{width:96px;height:96px;border-radius:12px;object-fit:cover;background:#333}
  h1{font-size:28px;margin:0}
  table{width:100%;border-collapse:collapse;margin-top:16px}
  td{padding:6px 10px;border-bottom:1px solid #3a352c}
  td.k{color:#c9b27a;width:40%}
</style></head>
<body><div class="card">
  <div class="head"><img src="{{mugshot}}"><h1>{{name}}</h1></div>
  <table>{{stats_rows}}</table>
</div></body></html>
```

- [ ] **Step 4: Write `trpg_cards.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_cards.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add trpg_cards.py assets/card.html tests/test_cards.py
git commit -m "feat: character card HTML fill + lossless WebP re-encode"
```

---

### Task 9: Full config model, lifecycle & per-stream runtime state (`plugin.py`)

**Files:**
- Modify: `maibot-trpg-plugin/plugin.py`
- Modify: `maibot-trpg-plugin/config.default.toml` (+ copy to `config.toml`)
- Test: `maibot-trpg-plugin/tests/test_config.py`

**Interfaces:**
- Produces (on `MaiTRPGPlugin`): `self.config.plugin.{enabled,config_version,maibot_plays}`, `self.config.gm.{main_gm_prompt,gm_model,temperature,max_tokens,timeout_seconds}`, `self.config.loop.{inactivity_flush_seconds,ooc_marker,max_consecutive_auto}`, `self.config.context.char_budget`, `self.config.storage.data_dir`; helpers `self._data_root() -> Path`, `self._paths(stream_id, session_id) -> trpg_storage.Paths`; per-stream runtime dicts `self._timers`, `self._buffers`, `self._consecutive_auto`, `self._flush_locks`.

- [ ] **Step 1: Write the failing test**

```python
def test_config_defaults():
    import plugin
    inst = plugin.create_plugin()
    cfg = plugin.MaiTRPGConfig()
    assert cfg.plugin.maibot_plays is True
    assert cfg.gm.main_gm_prompt.strip()           # ships a default zh-CN GM prompt
    assert cfg.loop.inactivity_flush_seconds >= 5
    assert cfg.loop.ooc_marker == "/ooc"
    assert cfg.context.char_budget >= 10000


def test_data_root_defaults_to_plugin_data(tmp_path, monkeypatch):
    import plugin
    inst = plugin.create_plugin()
    root = inst._data_root()
    assert root.name == "data"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'MaiTRPGConfig' object has no attribute 'gm'`.

- [ ] **Step 3: Extend config sections in `plugin.py`** (add after `PluginSection`, before `MaiTRPGConfig`)

```python
DEFAULT_GM_PROMPT = (
    "你是一位资深的跑团主持人（GM）。你负责描述场景、扮演 NPC、推进剧情，"
    "依据玩家行动给出生动、公正的叙事。你只负责叙事与裁定，绝不替玩家做决定，"
    "也绝不自行编造骰值——需要检定时用掷骰协议请求掷骰。语言：简体中文。"
)


class GMSection(PluginConfigBase):
    __ui_label__ = "GM 设置"

    main_gm_prompt: str = Field(default=DEFAULT_GM_PROMPT, description="GM 主提示词（机制与人设，可改）")
    gm_model: str = Field(default="replyer", description="GM 智能体模型：任务名或具体模型名")
    temperature: float = Field(default=0.8, description="GM 叙事温度")
    max_tokens: int = Field(default=4000, description="单次 GM 生成最大 token，<=0 交由宿主")
    timeout_seconds: int = Field(default=300, description="单次 GM 生成超时（秒），<=0 交由宿主默认值")


class LoopSection(PluginConfigBase):
    __ui_label__ = "回合循环"

    inactivity_flush_seconds: int = Field(default=45, description="台面静默多少秒后自动把发言批处理交给 GM")
    ooc_marker: str = Field(default="/ooc", description="场外发言前缀（也支持 (( )) 包裹）")
    max_consecutive_auto: int = Field(default=2, description="无真人行动时允许的最大连续自动推进次数")


class ContextSection(PluginConfigBase):
    __ui_label__ = "上下文"

    char_budget: int = Field(default=120000, description="GM 上下文字符预算（bible 置顶，超出裁剪最旧回合）")


class StorageSection(PluginConfigBase):
    __ui_label__ = "存储"

    data_dir: str = Field(default="", description="数据根目录；留空＝插件目录下 data/")


class MaiTRPGConfig(PluginConfigBase):
    plugin: PluginSection = Field(default_factory=PluginSection)
    gm: GMSection = Field(default_factory=GMSection)
    loop: LoopSection = Field(default_factory=LoopSection)
    context: ContextSection = Field(default_factory=ContextSection)
    storage: StorageSection = Field(default_factory=StorageSection)
```

- [ ] **Step 4: Extend `MaiTRPGPlugin.__init__` and add helpers** (in `plugin.py`)

Update the top imports to add: `import asyncio`, `from typing import Any`, and `import trpg_storage`. Then:

```python
    def __init__(self) -> None:
        super().__init__()
        self._plugin_dir = Path(__file__).resolve().parent
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._buffers: dict[str, Any] = {}            # stream_id -> trpg_batch.BatchBuffer
        self._consecutive_auto: dict[str, int] = {}
        self._flush_locks: dict[str, asyncio.Lock] = {}

    def _data_root(self) -> Path:
        custom = (self.config.storage.data_dir or "").strip()
        return Path(custom).expanduser() if custom else self._plugin_dir / "data"

    def _paths(self, stream_id: str, session_id: str) -> "trpg_storage.Paths":
        return trpg_storage.Paths(self._data_root(), stream_id, session_id)
```

- [ ] **Step 5: Update `config.default.toml`** to include the new sections with the defaults above (`[gm]`, `[loop]`, `[context]`, `[storage]`), and copy to `config.toml`.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add plugin.py config.default.toml config.toml tests/test_config.py
git commit -m "feat: full config model (gm/loop/context/storage) + runtime state + data root"
```

---

### Task 10: Session tools & commands (`plugin.py`)

**Files:**
- Modify: `maibot-trpg-plugin/plugin.py`
- Test: `maibot-trpg-plugin/tests/test_session_tools.py`

**Interfaces:**
- Consumes: `trpg_storage`, `trpg_session`, the config/runtime from Task 9.
- Produces (methods on the plugin; tools return `dict` with `success`/`content`):
  - Helpers: `_resolve_stream_id(kwargs) -> str` (mirror maibook), `_active_session_id(stream_id) -> str | None` (the lone `running`/`ready`/`setup` session, or the most recent), `_load_meta(stream_id, sid) -> dict`, `_save_meta(stream_id, sid, meta)`.
  - Tools: `session_create(title, **kw)`, `session_list(**kw)`, `session_start(session=None, **kw)`, `session_stop(session=None, **kw)`.
  - Commands: `/session create|list|start|stop`, `/join`.

Add imports: `import trpg_session`, and the SDK decorator/types line (mirror maibook): `from maibot_sdk import Command, Field, MaiBotPlugin, PluginConfigBase, Tool` plus `from maibot_sdk import ToolParameterInfo, ToolParamType` (verify exact import path against maibook's import block).

- [ ] **Step 1: Write the failing test**

```python
import asyncio
import types


class FakeSend:
    def __init__(self): self.sent = []
    async def text(self, content, stream_id): self.sent.append((stream_id, content))


class FakeLogger:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


def _plugin(tmp_path):
    import plugin
    inst = plugin.create_plugin()
    inst.ctx = types.SimpleNamespace(send=FakeSend(), logger=FakeLogger())
    inst.config.storage.data_dir = str(tmp_path)
    return inst


def test_session_create_then_list(tmp_path):
    inst = _plugin(tmp_path)
    r = asyncio.run(inst.session_create(title="初章", stream_id="g1"))
    assert r["success"]
    lst = asyncio.run(inst.session_list(stream_id="g1"))
    assert "初章" in lst["content"]


def test_session_start_blocked_by_gate(tmp_path):
    inst = _plugin(tmp_path)
    asyncio.run(inst.session_create(title="初章", stream_id="g1"))
    r = asyncio.run(inst.session_start(stream_id="g1"))
    assert not r["success"]
    assert "世界设定" in r["content"] or "未完成" in r["content"]


def test_session_create_rejects_empty_title(tmp_path):
    inst = _plugin(tmp_path)
    r = asyncio.run(inst.session_create(title="  ", stream_id="g1"))
    assert not r["success"]  # no silent success on empty input
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_session_tools.py -v`
Expected: FAIL — `AttributeError: 'MaiTRPGPlugin' object has no attribute 'session_create'`.

- [ ] **Step 3: Add session helpers + tools to `plugin.py`**

```python
    @staticmethod
    def _resolve_stream_id(kwargs: dict[str, Any]) -> str:
        for key in ("stream_id", "session_stream", "chat_id"):
            val = kwargs.get(key)
            if val:
                return str(val)
        return ""

    def _maibot_member(self) -> str | None:
        return "麦麦" if self.config.plugin.maibot_plays else None

    def _load_meta(self, stream_id: str, sid: str) -> dict[str, Any]:
        return trpg_storage.read_toml(self._paths(stream_id, sid).session_toml)

    def _save_meta(self, stream_id: str, sid: str, meta: dict[str, Any]) -> None:
        trpg_storage.write_toml(self._paths(stream_id, sid).session_toml, meta)

    def _active_session_id(self, stream_id: str, prefer: str | None = None) -> str | None:
        sessions = trpg_storage.list_sessions(self._data_root(), stream_id)
        if prefer:
            return prefer if any(s["session_id"] == prefer for s in sessions) else None
        for status in (trpg_session.RUNNING, trpg_session.READY, trpg_session.SETUP):
            for s in sessions:
                if s["status"] == status:
                    return s["session_id"]
        return sessions[-1]["session_id"] if sessions else None

    @Tool("session_create",
          brief_description="【麦麦跑团/MaiTRPG·会话】在本聊天新建一场跑团会话（初始 setup，需补全 bible 与角色卡后才能开始）。",
          parameters=[ToolParameterInfo(name="title", param_type=ToolParamType.STRING, required=True, description="会话标题")])
    async def session_create(self, title: str = "", **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        title = str(title or "").strip()
        if not stream_id:
            return {"success": False, "content": "无法确定当前聊天流。"}
        if not title:
            return {"success": False, "content": "会话标题不能为空。"}
        sid = trpg_storage.safe_component(title) or "session"
        if self._load_meta(stream_id, sid):
            return {"success": False, "content": f"已存在同名会话：{sid}"}
        meta = trpg_session.new_session_meta(sid, title, maibot_member=self._maibot_member())
        self._save_meta(stream_id, sid, meta)
        return {"success": True, "content": f"已创建会话《{title}》[{sid}]，状态 setup。请补全世界/剧情/GM子提示词并让玩家加入。"}

    @Tool("session_list",
          brief_description="【麦麦跑团/MaiTRPG·会话】列出本聊天的所有会话及状态（含已停止、可重启的会话）。",
          parameters=[])
    async def session_list(self, **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        sessions = trpg_storage.list_sessions(self._data_root(), stream_id)
        if not sessions:
            return {"success": True, "content": "本聊天还没有任何跑团会话。"}
        lines = [f"·《{s['title']}》[{s['session_id']}] 状态={s['status']} 成员={len(s['members'])}" for s in sessions]
        return {"success": True, "content": "本聊天的跑团会话：\n" + "\n".join(lines)}

    @Tool("session_start",
          brief_description="【麦麦跑团/MaiTRPG·会话】开始/重启一场会话——会先跑就绪门禁，未通过则报告缺什么。",
          parameters=[ToolParameterInfo(name="session", param_type=ToolParamType.STRING, required=False, default="", description="会话ID，省略＝当前会话")])
    async def session_start(self, session: str = "", **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id, str(session).strip() or None)
        if not sid:
            return {"success": False, "content": "找不到会话，请先 session_create。"}
        report = self._run_ready_check(stream_id, sid)
        if not report.ok:
            return {"success": False, "content": "未通过就绪检查：\n- " + "\n- ".join(report.missing)}
        meta = self._load_meta(stream_id, sid)
        meta["status"] = trpg_session.RUNNING
        self._save_meta(stream_id, sid, meta)
        return {"success": True, "content": f"会话《{meta['title']}》已开始！台面就绪，开始你们的冒险吧。"}

    @Tool("session_stop",
          brief_description="【麦麦跑团/MaiTRPG·会话】停止当前会话（可日后 session_start 重启，会再次跑门禁）。",
          parameters=[ToolParameterInfo(name="session", param_type=ToolParamType.STRING, required=False, default="", description="会话ID，省略＝当前会话")])
    async def session_stop(self, session: str = "", **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id, str(session).strip() or None)
        if not sid:
            return {"success": False, "content": "找不到会话。"}
        meta = self._load_meta(stream_id, sid)
        meta["status"] = trpg_session.STOPPED
        self._save_meta(stream_id, sid, meta)
        return {"success": True, "content": f"会话《{meta['title']}》已停止。"}
```

> `_run_ready_check(stream_id, sid)` is implemented in Task 11 (it reads bible files + schema + sheets). For Task 10's tests, add a temporary minimal version that returns the gate result from `trpg_session.ready_check` with `bible_present` all-False and empty sheets — i.e. it correctly blocks. Replace it in Task 11. Add now:

```python
    def _run_ready_check(self, stream_id: str, sid: str):
        meta = self._load_meta(stream_id, sid)
        return trpg_session.ready_check(meta, bible_present={}, schema={}, sheets={})
```

- [ ] **Step 4: Add commands** (`/session …`, `/join`)

```python
    @Command("trpg_session_command", description="跑团会话管理", pattern=r"^/session\s+(create|list|start|stop)(?:\s+(.*))?$")
    async def cmd_session(self, **kwargs: Any) -> Any:
        stream_id = self._resolve_stream_id(kwargs)
        groups = kwargs.get("matched_groups") or kwargs.get("groups") or ()
        action = groups[0] if groups else ""
        arg = (groups[1] if len(groups) > 1 else "") or ""
        if action == "create":
            res = await self.session_create(title=arg, stream_id=stream_id)
        elif action == "list":
            res = await self.session_list(stream_id=stream_id)
        elif action == "start":
            res = await self.session_start(session=arg, stream_id=stream_id)
        else:
            res = await self.session_stop(session=arg, stream_id=stream_id)
        await self.ctx.send.text(res["content"], stream_id)
        return None

    @Command("trpg_join_command", description="加入当前跑团会话", pattern=r"^/join\s*$")
    async def cmd_join(self, **kwargs: Any) -> Any:
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id)
        if not sid:
            await self.ctx.send.text("本聊天还没有跑团会话，先让麦麦或管理员 /session create。", stream_id)
            return None
        member = str(kwargs.get("user_id") or kwargs.get("sender_id") or "").strip()
        if not member:
            await self.ctx.send.text("无法识别你的身份，加入失败。", stream_id)
            return None
        meta = trpg_session.add_member(self._load_meta(stream_id, sid), member)
        self._save_meta(stream_id, sid, meta)
        await self.ctx.send.text(f"{member} 已加入会话，请用 /sheet 完成你的角色卡后才能开始/继续。", stream_id)
        return None
```

> The exact kwarg names for command regex groups and sender identity (`matched_groups`/`groups`, `user_id`/`sender_id`) must be verified against the SDK during implementation (read `maibot-plugin-sdk/docs/guide.md` Command section + an existing plugin's command). Adjust the two `.get(...)` fallback chains to the real keys; keep them defensive.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_session_tools.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add plugin.py tests/test_session_tools.py
git commit -m "feat: session_ tools + /session and /join commands"
```

---

### Task 11: Bible & sheet tools (`plugin.py`), real ready-check

**Files:**
- Modify: `maibot-trpg-plugin/plugin.py`
- Test: `maibot-trpg-plugin/tests/test_bible_sheet_tools.py`

**Interfaces:**
- Consumes: `trpg_schema`, `trpg_cards`, `trpg_storage`, Task 10 helpers.
- Produces:
  - `_bible_present(stream_id, sid) -> dict[str,bool]` (checks `bible/world.md`, `plot.md`, `gm_subprompt.md` non-empty).
  - `_load_schema(stream_id, sid) -> dict`, `_load_sheets(stream_id, sid) -> dict[str,dict]`.
  - Replace `_run_ready_check` with the real one (reads bible/schema/sheets).
  - Tools `bible_world`, `bible_plot`, `bible_gm`, `bible_check`; `sheet_schema`, `sheet_edit`, `sheet_render`, `sheet_mugshot`.

Add `import trpg_cards`, `import trpg_schema`.

- [ ] **Step 1: Write the failing test**

```python
import asyncio
import types


class FakeRender:
    async def html2png(self, html, viewport=None):
        import base64, io
        from PIL import Image
        buf = io.BytesIO(); Image.new("RGB", (10, 10), (255, 255, 255)).save(buf, format="PNG")
        return {"image_base64": base64.b64encode(buf.getvalue()).decode("ascii")}


class FakeSend:
    def __init__(self): self.images = []
    async def text(self, content, stream_id): pass
    async def image(self, image_base64, stream_id, **kw): self.images.append(image_base64)


class FakeLogger:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


def _plugin(tmp_path):
    import plugin
    inst = plugin.create_plugin()
    inst.ctx = types.SimpleNamespace(send=FakeSend(), render=FakeRender(), logger=FakeLogger())
    inst.config.storage.data_dir = str(tmp_path)
    asyncio.run(inst.session_create(title="局", stream_id="g1"))
    return inst


def test_bible_writes_and_check_progresses(tmp_path):
    inst = _plugin(tmp_path)
    asyncio.run(inst.session_start(stream_id="g1"))  # blocked
    asyncio.run(inst.bible_world(text="高塔世界", stream_id="g1"))
    asyncio.run(inst.bible_plot(text="寻找圣杯", stream_id="g1"))
    asyncio.run(inst.bible_gm(text="偏严肃", stream_id="g1"))
    chk = asyncio.run(inst.bible_check(stream_id="g1"))
    # bible done, but no players with complete cards yet -> still not ok
    assert "未完成" in chk["content"] or "没有任何玩家" in chk["content"]


def test_sheet_edit_then_render(tmp_path):
    inst = _plugin(tmp_path)
    # join a human, then fill their sheet
    meta = inst._load_meta("g1", "局")
    import trpg_session
    inst._save_meta("g1", "局", trpg_session.add_member(meta, "u1"))
    r = asyncio.run(inst.sheet_edit(fields={"name": "阿强", "hp": 12}, member="u1", stream_id="g1"))
    assert r["success"]
    rr = asyncio.run(inst.sheet_render(member="u1", stream_id="g1"))
    assert rr["success"] and inst.ctx.send.images  # an image was sent


def test_bible_world_rejects_empty(tmp_path):
    inst = _plugin(tmp_path)
    r = asyncio.run(inst.bible_world(text="   ", stream_id="g1"))
    assert not r["success"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_bible_sheet_tools.py -v`
Expected: FAIL — `AttributeError: ... 'bible_world'`.

- [ ] **Step 3: Add bible/sheet helpers + real ready-check to `plugin.py`**

```python
    def _bible_present(self, stream_id: str, sid: str) -> dict[str, bool]:
        p = self._paths(stream_id, sid)
        present = {}
        for key, fname in (("world", "world.md"), ("plot", "plot.md"), ("gm_subprompt", "gm_subprompt.md")):
            f = p.bible_file(fname)
            present[key] = f.exists() and bool(f.read_text(encoding="utf-8").strip())
        return present

    def _load_schema(self, stream_id: str, sid: str) -> dict[str, Any]:
        data = trpg_storage.read_toml(self._paths(stream_id, sid).bible_file("stat_schema.toml"))
        return trpg_schema.resolve_schema(data or None)

    def _load_sheets(self, stream_id: str, sid: str) -> dict[str, dict]:
        p = self._paths(stream_id, sid)
        out: dict[str, dict] = {}
        if p.characters_dir.exists():
            for child in p.characters_dir.glob("*.toml"):
                out[child.stem] = trpg_storage.read_toml(child)
        return out

    def _run_ready_check(self, stream_id: str, sid: str):
        meta = self._load_meta(stream_id, sid)
        return trpg_session.ready_check(
            meta,
            bible_present=self._bible_present(stream_id, sid),
            schema=self._load_schema(stream_id, sid),
            sheets=self._load_sheets(stream_id, sid),
        )

    def _write_bible(self, stream_id: str, key_fname: str, text: str, *, append: bool) -> None:
        sid = self._active_session_id(stream_id)
        f = self._paths(stream_id, sid).bible_file(key_fname)
        f.parent.mkdir(parents=True, exist_ok=True)
        if append and f.exists():
            text = f.read_text(encoding="utf-8").rstrip() + "\n\n" + text
        f.write_text(text.strip() + "\n", encoding="utf-8")
```

Bible tools (each rejects empty `text`):

```python
    @Tool("bible_world",
          brief_description="【麦麦跑团/MaiTRPG·设定】写入/追加世界设定到 bible（可多次累积）。",
          parameters=[ToolParameterInfo(name="text", param_type=ToolParamType.STRING, required=True, description="世界设定文本"),
                      ToolParameterInfo(name="append", param_type=ToolParamType.BOOLEAN, required=False, default=True, description="是否追加（默认追加）")])
    async def bible_world(self, text: str = "", append: bool = True, **kwargs: Any) -> dict[str, Any]:
        return await self._bible_tool(kwargs, "world.md", text, append, "世界设定")

    @Tool("bible_plot",
          brief_description="【麦麦跑团/MaiTRPG·设定】写入/追加剧情与钩子到 bible。",
          parameters=[ToolParameterInfo(name="text", param_type=ToolParamType.STRING, required=True, description="剧情/钩子文本"),
                      ToolParameterInfo(name="append", param_type=ToolParamType.BOOLEAN, required=False, default=True, description="是否追加")])
    async def bible_plot(self, text: str = "", append: bool = True, **kwargs: Any) -> dict[str, Any]:
        return await self._bible_tool(kwargs, "plot.md", text, append, "剧情")

    @Tool("bible_gm",
          brief_description="【麦麦跑团/MaiTRPG·设定】写入本场 GM 子提示词（基调/主题/特殊裁定；就绪门禁项）。",
          parameters=[ToolParameterInfo(name="text", param_type=ToolParamType.STRING, required=True, description="GM 子提示词文本"),
                      ToolParameterInfo(name="append", param_type=ToolParamType.BOOLEAN, required=False, default=False, description="是否追加（默认覆盖）")])
    async def bible_gm(self, text: str = "", append: bool = False, **kwargs: Any) -> dict[str, Any]:
        return await self._bible_tool(kwargs, "gm_subprompt.md", text, append, "GM 子提示词")

    async def _bible_tool(self, kwargs, fname, text, append, label) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        text = str(text or "").strip()
        if not self._active_session_id(stream_id):
            return {"success": False, "content": "没有可写入的会话，请先 session_create。"}
        if not text:
            return {"success": False, "content": f"{label}内容不能为空。"}
        self._write_bible(stream_id, fname, text, append=append)
        return {"success": True, "content": f"已写入{label}。"}

    @Tool("bible_check",
          brief_description="【麦麦跑团/MaiTRPG·设定】检查就绪门禁是否通过（世界/剧情/GM子提示词/属性schema/全员角色卡）。",
          parameters=[])
    async def bible_check(self, **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id)
        if not sid:
            return {"success": False, "content": "没有会话。"}
        report = self._run_ready_check(stream_id, sid)
        if report.ok:
            return {"success": True, "content": "就绪门禁已通过，可以 session_start 开始。"}
        return {"success": True, "content": "尚未就绪，仍缺：\n- " + "\n- ".join(report.missing)}
```

Sheet tools:

```python
    @Tool("sheet_schema",
          brief_description="【麦麦跑团/MaiTRPG·角色卡】查看或设置属性 schema（mode: view/default/custom/edit）。",
          parameters=[ToolParameterInfo(name="mode", param_type=ToolParamType.STRING, required=False, default="view", description="view/default/custom/edit", enum_values=["view", "default", "custom", "edit"]),
                      ToolParameterInfo(name="data", param_type=ToolParamType.STRING, required=False, default="", description="custom: 完整 fields JSON；edit: {add,modify,remove} JSON")])
    async def sheet_schema(self, mode: str = "view", data: str = "", **kwargs: Any) -> dict[str, Any]:
        import json
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id)
        if not sid:
            return {"success": False, "content": "没有会话。"}
        path = self._paths(stream_id, sid).bible_file("stat_schema.toml")
        cur = self._load_schema(stream_id, sid)
        mode = str(mode or "view").strip().lower()
        if mode == "view":
            return {"success": True, "content": "当前字段：" + trpg_gm.schema_summary(cur)}
        if mode == "default":
            trpg_storage.write_toml(path, trpg_schema.resolve_schema(None))
            return {"success": True, "content": "已重置为默认 schema。"}
        if mode == "custom":
            parsed = json.loads(data) if data.strip() else {}
            trpg_storage.write_toml(path, trpg_schema.resolve_schema(parsed))
            return {"success": True, "content": "已设置自定义 schema。"}
        if mode == "edit":
            spec = json.loads(data) if data.strip() else {}
            new = trpg_schema.apply_edits(cur, add=spec.get("add", []), modify=spec.get("modify", []), remove=spec.get("remove", []))
            trpg_storage.write_toml(path, new)
            return {"success": True, "content": "已更新 schema：" + trpg_gm.schema_summary(new)}
        return {"success": False, "content": "未知 mode。"}

    @Tool("sheet_edit",
          brief_description="【麦麦跑团/MaiTRPG·角色卡】设置某玩家角色卡字段（按 schema 校验类型）。",
          parameters=[ToolParameterInfo(name="fields", param_type=ToolParamType.OBJECT, required=True, description="字段键值对，如 {name:..,hp:..}"),
                      ToolParameterInfo(name="member", param_type=ToolParamType.STRING, required=False, default="", description="玩家ID，省略＝当前发言者")])
    async def sheet_edit(self, fields: Any = None, member: str = "", **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id)
        member = str(member or kwargs.get("user_id") or "").strip()
        if not sid or not member:
            return {"success": False, "content": "缺少会话或玩家身份。"}
        if not isinstance(fields, dict) or not fields:
            return {"success": False, "content": "fields 不能为空。"}
        schema = self._load_schema(stream_id, sid)
        path = self._paths(stream_id, sid).character_toml(member)
        sheet = trpg_storage.read_toml(path) or trpg_schema.blank_sheet(schema)
        sheet.update(fields)
        problems = trpg_schema.validate_sheet(sheet, schema)
        trpg_storage.write_toml(path, sheet)
        if trpg_schema.sheet_complete(sheet, schema):
            meta = trpg_session.mark_card_done(self._load_meta(stream_id, sid), member)
            self._save_meta(stream_id, sid, meta)
            return {"success": True, "content": f"{member} 的角色卡已完成。"}
        return {"success": True, "content": f"已更新，但角色卡仍未完成：{('；'.join(problems)) or '继续补全'}"}

    @Tool("sheet_render",
          brief_description="【麦麦跑团/MaiTRPG·角色卡】渲染某玩家角色卡为图片并发到聊天。",
          parameters=[ToolParameterInfo(name="member", param_type=ToolParamType.STRING, required=False, default="", description="玩家ID，省略＝当前发言者")])
    async def sheet_render(self, member: str = "", **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id)
        member = str(member or kwargs.get("user_id") or "").strip()
        if not sid or not member:
            return {"success": False, "content": "缺少会话或玩家身份。"}
        schema = self._load_schema(stream_id, sid)
        sheet = trpg_storage.read_toml(self._paths(stream_id, sid).character_toml(member))
        if not sheet:
            return {"success": False, "content": f"{member} 还没有角色卡。"}
        img_b64 = await self._render_card(stream_id, sid, member, sheet, schema)
        if not img_b64:
            return {"success": False, "content": "渲染失败。"}
        await self.ctx.send.image(img_b64, stream_id)
        return {"success": True, "content": f"已发送 {member} 的角色卡。"}

    @Tool("sheet_mugshot",
          brief_description="【麦麦跑团/MaiTRPG·角色卡】把图片（data URI/base64）设为某玩家角色卡头像。",
          parameters=[ToolParameterInfo(name="image", param_type=ToolParamType.STRING, required=True, description="图片 data URI 或 base64"),
                      ToolParameterInfo(name="member", param_type=ToolParamType.STRING, required=False, default="", description="玩家ID，省略＝当前发言者")])
    async def sheet_mugshot(self, image: str = "", member: str = "", **kwargs: Any) -> dict[str, Any]:
        stream_id = self._resolve_stream_id(kwargs)
        sid = self._active_session_id(stream_id)
        member = str(member or kwargs.get("user_id") or "").strip()
        image = str(image or "").strip()
        if not sid or not member:
            return {"success": False, "content": "缺少会话或玩家身份。"}
        if not image:
            return {"success": False, "content": "未提供图片。"}
        uri = image if image.startswith("data:") else f"data:image/png;base64,{image}"
        self._paths(stream_id, sid).character_toml(member).parent.mkdir(parents=True, exist_ok=True)
        (self._paths(stream_id, sid).characters_dir / f"{trpg_storage.safe_component(member)}.mugshot").write_text(uri, encoding="utf-8")
        return {"success": True, "content": f"已设置 {member} 的头像。"}

    async def _render_card(self, stream_id, sid, member, sheet, schema) -> str:
        template = (self._plugin_dir / "assets" / "card.html").read_text(encoding="utf-8")
        mug_path = self._paths(stream_id, sid).characters_dir / f"{trpg_storage.safe_component(member)}.mugshot"
        mug = mug_path.read_text(encoding="utf-8") if mug_path.exists() else ""
        html = trpg_cards.build_card_html(template, sheet=sheet, schema=schema, mugshot_uri=mug)
        rendered = await self.ctx.render.html2png(html, viewport={"width": 520, "height": 1, "device_scale_factor": 1})
        png_b64 = rendered.get("image_base64", "") if isinstance(rendered, dict) else str(rendered or "")
        if not png_b64:
            return ""
        return trpg_cards.to_compact_webp(png_b64, self.ctx.logger)
```

Add `import trpg_gm` to the top imports (used by `sheet_schema`).

> Verify the exact return shape of `ctx.render.html2png` (key `image_base64` vs other) and `ctx.send.image` signature against `maibot-impression-card-plugin/plugin.py` during implementation; adjust the two access points. `ToolParamType.OBJECT` for `fields` — confirm the enum member name in the SDK (`OBJECT`/`DICT`); fall back to STRING + JSON parse if absent.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_bible_sheet_tools.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add plugin.py tests/test_bible_sheet_tools.py
git commit -m "feat: bible_ & sheet_ tools + real ready-check (bible+schema+cards)"
```

---

### Task 12: Intake, debounce, and the flush pipeline (`plugin.py`)

**Files:**
- Modify: `maibot-trpg-plugin/plugin.py`
- Test: `maibot-trpg-plugin/tests/test_flush_pipeline.py`

**Interfaces:**
- Consumes: `trpg_batch`, `trpg_context`, `trpg_gm`, `trpg_dice`, all prior helpers.
- Produces:
  - `@EventHandler(ON_MESSAGE)` `on_message` — buffers in-character human messages for streams with a `running` session; arms the debounce timer; honors OOC + `story_held`.
  - `@EventHandler(AFTER_SEND)` (or `send_service.after_send` hook) `on_after_send` — buffers MaiBot's own outbound replies as `maibot` entries, **excluding** plugin-tagged GM sends.
  - `@Command("/gm go")` `cmd_flush` — forces an immediate flush.
  - `async _flush_stream(stream_id)` — the table-turn pipeline (idempotent per stream via `_flush_locks`).
  - `async _run_gm(stream_id, sid, messages) -> str` — single `ctx.llm.generate` call wrapper.
  - `_buffer_for(stream_id) -> BatchBuffer`, `_arm_timer(stream_id)`.

Add imports: `import random`, `import trpg_batch`, `import trpg_context`, `import trpg_dice`, and `from maibot_sdk import EventHandler` + `from maibot_sdk.types import EventType`. (`trpg_storage`/`trpg_session`/`trpg_schema`/`trpg_gm` were imported in earlier tasks.)

- [ ] **Step 1: Write the failing test** (drives the whole pipeline with a fake LLM that emits a roll marker)

```python
import asyncio
import types

import trpg_session


class FakeLLM:
    def __init__(self):
        self.calls = 0
    async def generate(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {"content": "你撬动锁芯。\n===ROLL===\nactor: u1\nmodifier: 2\ndc: 10\nadvantage: 0\nreason: 撬锁\n===END==="}
        return {"content": "锁应声而开，门后是幽深的走廊。\n===WORLD_STATE===\n队伍进入走廊。\n===END==="}


class FakeSend:
    def __init__(self): self.texts = []
    async def text(self, content, stream_id): self.texts.append(content)
    async def image(self, *a, **k): pass


class FakeMaisaka:
    def __init__(self):
        self.context = types.SimpleNamespace(append=self._noop)
        self.proactive = types.SimpleNamespace(trigger=self._noop)
    async def _noop(self, **k): pass


class FakeLogger:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


def _running_plugin(tmp_path):
    import plugin
    inst = plugin.create_plugin()
    inst.ctx = types.SimpleNamespace(send=FakeSend(), llm=FakeLLM(), maisaka=FakeMaisaka(), logger=FakeLogger())
    inst.config.storage.data_dir = str(tmp_path)
    asyncio.run(inst.session_create(title="局", stream_id="g1"))
    # complete bible
    for fn, t in (("world.md", "高塔"), ("plot.md", "圣杯"), ("gm_subprompt.md", "严肃")):
        inst._write_bible("g1", fn, t, append=False)
    # add human u1 with complete sheet
    meta = trpg_session.add_member(inst._load_meta("g1", "局"), "u1")
    inst._save_meta("g1", "局", meta)
    asyncio.run(inst.sheet_edit(fields={"name": "阿强"}, member="u1", stream_id="g1"))
    # 麦麦默认作为玩家自动加入，其角色卡同样必须完成门禁才放行（她用 sheet_edit 自填，无特权）
    asyncio.run(inst.sheet_edit(fields={"name": "麦麦"}, member="麦麦", stream_id="g1"))
    asyncio.run(inst.session_start(stream_id="g1"))
    return inst


def test_flush_produces_narration_roll_and_world_state(tmp_path):
    inst = _running_plugin(tmp_path)
    buf = inst._buffer_for("g1")
    buf.add(__import__("trpg_batch").Entry("u1", "human", "我撬锁"))
    asyncio.run(inst._flush_stream("g1"))
    # narration sent (markers stripped), roll injected, world_state persisted
    joined = "\n".join(inst.ctx.send.texts)
    assert "锁应声而开" in joined
    assert "===ROLL===" not in joined
    audit = inst._paths("g1", "局").audit_log.read_text(encoding="utf-8")
    assert "u1" in audit and "DC10" in audit
    assert "走廊" in inst._paths("g1", "局").world_state.read_text(encoding="utf-8")


def test_runaway_guard_blocks_maibot_only_batch(tmp_path):
    inst = _running_plugin(tmp_path)
    inst._consecutive_auto["g1"] = inst.config.loop.max_consecutive_auto
    buf = inst._buffer_for("g1")
    buf.add(__import__("trpg_batch").Entry("麦麦", "maibot", "我也撬"))
    asyncio.run(inst._flush_stream("g1"))
    assert inst.ctx.send.texts == []  # no GM advance without a human under cap
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_flush_pipeline.py -v`
Expected: FAIL — `AttributeError: ... '_buffer_for'`.

- [ ] **Step 3: Add intake + pipeline to `plugin.py`**

```python
    def _buffer_for(self, stream_id: str):
        if stream_id not in self._buffers:
            self._buffers[stream_id] = trpg_batch.BatchBuffer()
        return self._buffers[stream_id]

    def _running_session(self, stream_id: str) -> str | None:
        for s in trpg_storage.list_sessions(self._data_root(), stream_id):
            if s["status"] == trpg_session.RUNNING:
                return s["session_id"]
        return None

    def _arm_timer(self, stream_id: str) -> None:
        loop = asyncio.get_event_loop()
        if stream_id in self._timers:
            self._timers[stream_id].cancel()
        delay = max(5, int(self.config.loop.inactivity_flush_seconds))
        self._timers[stream_id] = loop.call_later(
            delay, lambda: asyncio.ensure_future(self._flush_stream(stream_id)))

    @EventHandler("trpg_intake", description="收集台面发言", event_type=EventType.ON_MESSAGE)
    async def on_message(self, message: Any = None, stream_id: str = "", **kwargs: Any) -> Any:
        if not message or not stream_id:
            return None
        sid = self._running_session(stream_id)
        if not sid:
            return None
        meta = self._load_meta(stream_id, sid)
        if trpg_session.story_held(meta):
            return None
        text = message.get("plain_text", "") if isinstance(message, dict) else ""
        author = str(message.get("user_id") or message.get("sender_id") or "") if isinstance(message, dict) else ""
        if not text or author not in meta["members"]:
            return None
        if trpg_batch.is_ooc(text, self.config.loop.ooc_marker):
            return None
        self._buffer_for(stream_id).add(trpg_batch.Entry(author, "human", trpg_batch.clean_action(text, self.config.loop.ooc_marker)))
        self._arm_timer(stream_id)
        return None

    @EventHandler("trpg_intake_mai", description="收集麦麦的扮演发言", event_type=EventType.AFTER_SEND)
    async def on_after_send(self, message: Any = None, stream_id: str = "", **kwargs: Any) -> Any:
        if not message or not stream_id:
            return None
        if isinstance(message, dict) and message.get("trpg_gm_narration"):
            return None  # 不要把 GM 旁白当成麦麦的玩家行动（防失控回环）
        sid = self._running_session(stream_id)
        if not sid:
            return None
        meta = self._load_meta(stream_id, sid)
        mai = self._maibot_member()
        if not mai or mai not in meta["members"] or trpg_session.story_held(meta):
            return None
        text = message.get("plain_text", "") if isinstance(message, dict) else ""
        if not text or trpg_batch.is_ooc(text, self.config.loop.ooc_marker):
            return None
        self._buffer_for(stream_id).add(trpg_batch.Entry(mai, "maibot", text))
        self._arm_timer(stream_id)
        return None

    @Command("trpg_flush_command", description="立即把当前台面交给 GM", pattern=r"^/gm\s+go\s*$")
    async def cmd_flush(self, **kwargs: Any) -> Any:
        stream_id = self._resolve_stream_id(kwargs)
        await self._flush_stream(stream_id)
        return None

    async def _run_gm(self, messages: list[dict], system_prompt: str) -> str:
        result = await self.ctx.llm.generate(
            task=self.config.gm.gm_model,
            system_prompt=system_prompt,
            messages=messages,
            temperature=self.config.gm.temperature,
            max_tokens=self.config.gm.max_tokens,
        )
        if isinstance(result, dict):
            return str(result.get("content", ""))
        return str(result or "")

    async def _flush_stream(self, stream_id: str) -> None:
        if stream_id in self._timers:
            self._timers.pop(stream_id).cancel()
        sid = self._running_session(stream_id)
        if not sid:
            return
        lock = self._flush_locks.setdefault(stream_id, asyncio.Lock())
        if lock.locked():
            return
        async with lock:
            buffer = self._buffer_for(stream_id)
            decision = trpg_batch.decide_advance(buffer, self._consecutive_auto.get(stream_id, 0),
                                                  self.config.loop.max_consecutive_auto)
            if not decision.advance:
                return
            batch = buffer.drain()
            self._consecutive_auto[stream_id] = 0 if any(e.kind == "human" for e in batch) \
                else self._consecutive_auto.get(stream_id, 0) + 1

            p = self._paths(stream_id, sid)
            schema = self._load_schema(stream_id, sid)
            bible = {k: (p.bible_file(f"{k}.md").read_text(encoding="utf-8") if p.bible_file(f"{k}.md").exists() else "")
                     for k in ("world", "plot")}
            gm_sub = p.bible_file("gm_subprompt.md").read_text(encoding="utf-8") if p.bible_file("gm_subprompt.md").exists() else ""
            world_state = p.world_state.read_text(encoding="utf-8") if p.world_state.exists() else trpg_context.bible_block(bible)

            system_prompt = trpg_gm.build_system_prompt(self.config.gm.main_gm_prompt, gm_sub, trpg_gm.schema_summary(schema))
            messages = trpg_context.assemble_messages(world_state=world_state, recent_turns=[], batch=batch,
                                                      char_budget=self.config.context.char_budget)
            for e in batch:
                trpg_storage.append_line(p.episode_log(0), f"{e.author}（{e.kind}）：{e.text}")

            gm_text = await self._run_gm(messages, system_prompt)

            # resolve any roll requests, inject as system turns, re-generate once
            requests = trpg_gm.parse_roll_requests(gm_text)
            if requests:
                rng = random.Random()
                sys_entries: list = []
                for req in requests:
                    res = trpg_dice.check(req.modifier, req.dc, rng=rng, advantage=req.advantage)
                    line = trpg_gm.format_roll_result(req, res)
                    trpg_storage.append_line(p.audit_log, line)
                    sys_entries.append(trpg_batch.Entry("系统", "system", line))
                messages2 = trpg_context.assemble_messages(world_state=world_state, recent_turns=batch,
                                                           batch=sys_entries, char_budget=self.config.context.char_budget)
                gm_text = await self._run_gm(messages2, system_prompt)

            new_ws = trpg_gm.extract_world_state(gm_text)
            if new_ws:
                p.world_state.parent.mkdir(parents=True, exist_ok=True)
                p.world_state.write_text(new_ws + "\n", encoding="utf-8")

            narration = trpg_gm.strip_markers(gm_text)
            if narration:
                trpg_storage.append_line(p.episode_log(0), f"GM：{narration}")
                await self.ctx.send.text(f"【GM】{narration}", stream_id)
                # 唤醒麦麦以玩家身份回应（参照 maibook plugin.py:472-491）
                if self._maibot_member():
                    try:
                        await self.ctx.maisaka.context.append(
                            stream_id=stream_id,
                            segments=[{"type": "text", "content": f"[跑团|GM旁白] {narration}"}],
                            source_kind="plugin:maibot-trpg")
                        await self.ctx.maisaka.proactive.trigger(
                            stream_id=stream_id, intent="trpg_player_turn", reason="GM 推进了剧情，轮到你作为玩家行动")
                    except Exception as exc:  # noqa: BLE001
                        self.ctx.logger.warning("麦麦跑团：唤醒麦麦失败：%s", exc)
```

> **Tagging GM sends:** the `on_after_send` exclusion relies on the GM narration carrying a `trpg_gm_narration` marker. Verify how `ctx.send.text` lets a plugin attach metadata to its own outbound message (read the SDK `send` proxy + `AFTER_SEND` payload). If metadata can't be attached, fall back to comparing the outbound `plain_text` against the last narration string per stream (store `self._last_narration[stream_id]` and skip a matching outbound). Implement whichever the SDK supports; the test injects no AFTER_SEND so either works for the unit test, but the live guard must be real.
>
> Also verify the `ctx.llm.generate` keyword names (`task`/`system_prompt`/`messages`/`temperature`/`max_tokens`) against `maibot-plugin-sdk/docs/guide.md` and maibook's generate calls; adjust `_run_gm` to the real signature.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_flush_pipeline.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the whole suite**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest -v`
Expected: PASS (all tasks' tests).

- [ ] **Step 6: Commit**

```bash
git add plugin.py tests/test_flush_pipeline.py
git commit -m "feat: ON_MESSAGE intake, debounce flush, GM turn w/ authoritative roll injection + Mai wake-up"
```

---

### Task 13: Manifest-capability test, aggregate smoke test, README

**Files:**
- Modify: `maibot-trpg-plugin/tests/smoke_test.py`
- Create: `maibot-trpg-plugin/tests/test_manifest.py`
- Create: `maibot-trpg-plugin/README.md`

**Interfaces:**
- Produces: a test asserting declared `capabilities` ⊇ the `ctx.<cap>` names used in `plugin.py`; a README documenting tools/commands/config; `smoke_test.py` runs the full suite offline.

- [ ] **Step 1: Write the failing test** — `tests/test_manifest.py` (mirror impression-card's `test_manifest_capabilities_cover_usage`)

```python
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
```

- [ ] **Step 2: Run test to verify it fails (or passes) and reconcile**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest tests/test_manifest.py -v`
Expected: PASS. If `undeclared` fails, add the missing dotted capability (e.g. `send.image`) to `_manifest.json`; if `unused` fails, remove the declared-but-unused family. The Task 0 manifest already declares exactly the six dotted capabilities Phase 1 uses (`llm.generate`, `send.text`, `send.image`, `render.html2png`, `maisaka.context.append`, `maisaka.proactive.trigger`) → families `{llm, send, render, maisaka}`, which must equal the `self.ctx.<family>` names used in `plugin.py`.

- [ ] **Step 3: Make `smoke_test.py` run the full suite**

Append to `tests/smoke_test.py`:

```python
def test_full_suite_runs():
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-m", "pytest", str(ROOT / "tests"), "-q", "-p", "no:cacheprovider"],
                       cwd=str(ROOT))
    assert r.returncode == 0
```

(Keep the `__main__` block calling the Task-0 tests; the full-suite test is invoked under pytest only.)

- [ ] **Step 4: Write `README.md`** (zh-CN) covering: 概念（引擎/GM智能体/麦麦作为玩家）、工具一览（`session_`/`bible_`/`sheet_` 三类，每类 ≤4）、命令（`/session`、`/join`、`/sheet`、`/gm go`、`/ooc`、`/do`、`/say`）、就绪门禁、掷骰协议、配置项、`PYTHONPATH=.:../maibot-plugin-sdk python tests/smoke_test.py` 测试说明、软链部署（`ln -s ../../maibot-trpg-plugin MaiBot/plugins/maibot-trpg-plugin`）、Phase 2 路线图（`/dispute`+recall、规则书摄取、词典、地图、剧集摘要）。

- [ ] **Step 5: Run the full suite + lint**

Run: `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk pytest -v`
Expected: PASS (all). Optionally `uv run ruff check .` if ruff is available (line length 120).

- [ ] **Step 6: Commit**

```bash
git add tests/test_manifest.py tests/smoke_test.py README.md _manifest.json
git commit -m "test: manifest capability coverage + aggregate smoke test; docs: README"
```

---

## Verification (end-to-end)

1. **Offline (no Host):**
   `cd maibot-trpg-plugin && PYTHONPATH=.:../maibot-plugin-sdk python tests/smoke_test.py` → `OK`, and
   `PYTHONPATH=.:../maibot-plugin-sdk pytest -v` → all green. This exercises dice determinism, schema (default/semi/custom), session gate + new-player hold, batch/runaway guard, context budgeting, GM marker parsing, card render/WebP, every tool with a mocked `ctx`, and the full flush pipeline (narration + authoritative roll injection + world-state update).
2. **Live (in MaiBot):** symlink `ln -s ../../maibot-trpg-plugin MaiBot/plugins/maibot-trpg-plugin`, start the Host, then in a chat:
   `/session create 初章` → `/join` (as a human) → `sheet_edit`/`/sheet` to complete the card → `bible_world`/`bible_plot`/`bible_gm` (via MaiBot tools or commands) → `bible_check` (expect blocked until cards+bible done) → `/session start` → type an in-character action → wait `inactivity_flush_seconds` (or `/gm go`) → **【GM】** narration appears; an action needing a check shows the rolled result and writes `audit.log` → confirm MaiBot is nudged and replies in-character (and her reply, not the GM narration, is captured next turn) → `/session stop` → `/session list` shows it stopped → `/session start` re-runs the gate.

   During this pass, resolve the four flagged SDK-shape verifications (Command group/sender kwargs; `ctx.render.html2png` return key + `ctx.send.image` signature; `ToolParamType.OBJECT`; `ctx.llm.generate` kwargs + AFTER_SEND/own-send tagging) against the SDK and reference plugins, adjusting the marked access points.

## Out of scope (Phase 2, separate plan)

`/dispute` + recall over the transcript/audit log; rulebook URL ingestion → `rules.md`/`stat_schema.toml`/dictionary seeds; dictionary tools (`lore_`); map Markdown + render; episodes/scenes rolling summaries; optional `@HookHandler("maisaka.replyer.before_model_request")` scene injection. The transcript (`episodes/NN.log`) and `audit.log` are already written in Phase 1 so Phase-2 recall has data.
