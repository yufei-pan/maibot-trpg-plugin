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
