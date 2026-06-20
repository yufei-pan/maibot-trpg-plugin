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
