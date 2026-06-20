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
