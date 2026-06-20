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
