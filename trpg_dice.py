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
