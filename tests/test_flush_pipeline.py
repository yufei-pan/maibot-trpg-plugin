"""Task 12: 台面收集 → 去抖冲刷 → GM 回合全链路测试。"""

import asyncio
import types

import trpg_batch
import trpg_session


# ------------------------------------------------------------------ #
# Fakes — 匹配 SDK 的真实 ctx.llm.generate 签名
# ------------------------------------------------------------------ #
class FakeLLM:
    """模拟 ctx.llm.generate；第1次返回带 ROLL 标记，第2次返回叙事 + WORLD_STATE。

    真实签名：generate(prompt, model="", temperature=None, max_tokens=None, **kwargs)
    返回：{"success": True, "response": "...", "reasoning": "", "model": "..."}
    """

    def __init__(self):
        self.calls = 0

    async def generate(self, prompt=None, model="", temperature=None, max_tokens=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {
                "success": True,
                "response": (
                    "你撬动锁芯。\n"
                    "===ROLL===\n"
                    "actor: u1\n"
                    "modifier: 2\n"
                    "dc: 10\n"
                    "advantage: 0\n"
                    "reason: 撬锁\n"
                    "===END==="
                ),
                "reasoning": "",
                "model": model or "test-model",
            }
        return {
            "success": True,
            "response": "锁应声而开，门后是幽深的走廊。\n===WORLD_STATE===\n队伍进入走廊。\n===END===",
            "reasoning": "",
            "model": model or "test-model",
        }


class FakeSend:
    def __init__(self):
        self.texts: list[str] = []

    async def text(self, content, stream_id):
        self.texts.append(content)

    async def image(self, *a, **k):
        pass


class FakeMaisaka:
    def __init__(self):
        self.context = types.SimpleNamespace(append=self._noop)
        self.proactive = types.SimpleNamespace(trigger=self._noop)

    async def _noop(self, **k):
        pass


class FakeLogger:
    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


# ------------------------------------------------------------------ #
# 辅助：构建一个已 running 的插件实例
# ------------------------------------------------------------------ #
def _running_plugin(tmp_path):
    import plugin

    inst = plugin.create_plugin()
    inst._ctx = types.SimpleNamespace(
        send=FakeSend(), llm=FakeLLM(), maisaka=FakeMaisaka(), logger=FakeLogger()
    )
    cfg = plugin.MaiTRPGConfig()
    cfg.storage.data_dir = str(tmp_path)
    inst._plugin_config_instance = cfg

    asyncio.run(inst.session_create(title="局", stream_id="g1"))
    # 补全 bible
    for fn, t in (("world.md", "高塔"), ("plot.md", "圣杯"), ("gm_subprompt.md", "严肃")):
        inst._write_bible("g1", fn, t, append=False)
    # 加入人类玩家 u1 并补全角色卡
    meta = trpg_session.add_member(inst._load_meta("g1", "局"), "u1")
    inst._save_meta("g1", "局", meta)
    asyncio.run(inst.sheet_edit(fields={"name": "阿强"}, member="u1", stream_id="g1"))
    # 麦麦自动加入，同样需要完成角色卡
    asyncio.run(inst.sheet_edit(fields={"name": "麦麦"}, member="麦麦", stream_id="g1"))
    # 开始会话
    asyncio.run(inst.session_start(stream_id="g1"))
    return inst


# ------------------------------------------------------------------ #
# 测试
# ------------------------------------------------------------------ #
def test_flush_produces_narration_roll_and_world_state(tmp_path):
    """完整 GM 回合：人类行动 → buffer → flush → ROLL 请求 → 掷骰注入 →
    再生成 → 叙事送达（markers 已剥离）→ audit_log → world_state 更新。"""
    inst = _running_plugin(tmp_path)
    buf = inst._buffer_for("g1")
    buf.add(trpg_batch.Entry("u1", "human", "我撬锁"))
    asyncio.run(inst._flush_stream("g1"))
    # 叙事已发送（markers 已剥离），掷骰注入过，world_state 已持久化
    joined = "\n".join(inst.ctx.send.texts)
    assert "锁应声而开" in joined
    assert "===ROLL===" not in joined
    audit = inst._paths("g1", "局").audit_log.read_text(encoding="utf-8")
    assert "u1" in audit and "DC10" in audit
    assert "走廊" in inst._paths("g1", "局").world_state.read_text(encoding="utf-8")


def test_runaway_guard_blocks_maibot_only_batch(tmp_path):
    """防失控守卫：连续自动推进达上限 + 缓冲仅含 maibot 行动 → 不推进。"""
    inst = _running_plugin(tmp_path)
    inst._consecutive_auto["g1"] = inst.config.loop.max_consecutive_auto
    buf = inst._buffer_for("g1")
    buf.add(trpg_batch.Entry("麦麦", "maibot", "我也撬"))
    asyncio.run(inst._flush_stream("g1"))
    assert inst.ctx.send.texts == []  # 无真人行动且已达上限 → 不推进


# ------------------------------------------------------------------ #
# on_after_send HookHandler 测试
# ------------------------------------------------------------------ #
def _fake_send_message(session_id: str, text: str) -> dict:
    """构造与宿主 serialize_session_message 一致的 MessageDict。

    关键字段：processed_plain_text（文本）、session_id（聊天流 ID）。
    参考：MaiBot/src/plugin_runtime/host/message_utils.py:412-436
    """
    return {
        "message_id": "test-msg-001",
        "timestamp": "1719100000.0",
        "platform": "test",
        "message_info": {
            "user_info": {"user_id": "bot", "user_nickname": "麦麦"},
        },
        "raw_message": [],
        "is_mentioned": False,
        "is_at": False,
        "is_emoji": False,
        "is_picture": False,
        "is_command": False,
        "is_notify": False,
        "session_id": session_id,
        "processed_plain_text": text,
    }


def test_after_send_buffers_maibot_action(tmp_path):
    """sent=True + 非 GM 旁白 → 麦麦行动被收入 buffer。"""
    inst = _running_plugin(tmp_path)
    msg = _fake_send_message("g1", "我挥剑攻击")
    asyncio.run(inst.on_after_send(message=msg, sent=True))
    entries = list(inst._buffer_for("g1").entries)
    assert len(entries) == 1
    assert entries[0].kind == "maibot"
    assert entries[0].text == "我挥剑攻击"


def test_after_send_skips_own_gm_narration(tmp_path):
    """text 与 _last_narration 匹配 → 不缓冲（防止 GM 旁白被当做玩家行动）。"""
    inst = _running_plugin(tmp_path)
    narration = "【GM】你踏入黑暗的走廊。"
    inst._last_narration["g1"] = narration
    msg = _fake_send_message("g1", narration)
    asyncio.run(inst.on_after_send(message=msg, sent=True))
    entries = list(inst._buffer_for("g1").entries)
    assert len(entries) == 0


def test_after_send_skips_when_not_sent(tmp_path):
    """sent=False → 发送失败，不缓冲。"""
    inst = _running_plugin(tmp_path)
    msg = _fake_send_message("g1", "我挥剑")
    asyncio.run(inst.on_after_send(message=msg, sent=False))
    entries = list(inst._buffer_for("g1").entries)
    assert len(entries) == 0


# ------------------------------------------------------------------ #
# on_message HookHandler 测试
# ------------------------------------------------------------------ #
def _fake_inbound_message(session_id: str, text: str, user_id: str) -> dict:
    """构造与宿主 serialize_session_message 一致的入站 MessageDict。

    关键字段：session_id（聊天流）、processed_plain_text（文本）、
    message_info.user_info.user_id（发言者）。
    参考：MaiBot/src/plugin_runtime/host/message_utils.py:412-436
    """
    return {
        "message_id": "test-inbound-001",
        "timestamp": "1719100000.0",
        "platform": "test",
        "message_info": {
            "user_info": {"user_id": user_id, "user_nickname": user_id},
        },
        "raw_message": [],
        "is_mentioned": False,
        "is_at": False,
        "is_emoji": False,
        "is_picture": False,
        "is_command": False,
        "is_notify": False,
        "session_id": session_id,
        "processed_plain_text": text,
    }


def test_on_message_buffers_human_action(tmp_path):
    """入站人类发言（会话成员）→ human Entry 被缓冲。"""
    inst = _running_plugin(tmp_path)
    msg = _fake_inbound_message("g1", "我打开宝箱", "u1")
    asyncio.run(inst.on_message(message=msg))
    entries = list(inst._buffer_for("g1").entries)
    assert len(entries) == 1
    assert entries[0].kind == "human"
    assert entries[0].author == "u1"
    assert "打开宝箱" in entries[0].text


def test_on_message_skips_ooc(tmp_path):
    """OOC 标记的发言不缓冲。"""
    inst = _running_plugin(tmp_path)
    msg = _fake_inbound_message("g1", "/ooc 我去吃饭了", "u1")
    asyncio.run(inst.on_message(message=msg))
    entries = list(inst._buffer_for("g1").entries)
    assert len(entries) == 0


def test_on_message_skips_non_member(tmp_path):
    """非会话成员发言不缓冲。"""
    inst = _running_plugin(tmp_path)
    msg = _fake_inbound_message("g1", "我也想参加", "outsider")
    asyncio.run(inst.on_message(message=msg))
    entries = list(inst._buffer_for("g1").entries)
    assert len(entries) == 0
