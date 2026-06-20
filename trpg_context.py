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
