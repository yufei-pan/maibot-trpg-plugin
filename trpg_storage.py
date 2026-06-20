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
