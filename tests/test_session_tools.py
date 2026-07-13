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
    inst._ctx = types.SimpleNamespace(send=FakeSend(), logger=FakeLogger())
    cfg = plugin.MaiTRPGConfig()
    cfg.storage.data_dir = str(tmp_path)
    inst._plugin_config_instance = cfg
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


def test_session_list_rejects_empty_stream_id(tmp_path):
    """session_list（以及 session_start/stop）在 stream_id 无法解析时应返回失败，而非作用于幽灵路径。"""
    inst = _plugin(tmp_path)
    # 不传任何 stream_id 相关键 → _resolve_stream_id 返回 ""
    r = asyncio.run(inst.session_list())
    assert not r["success"]
    assert "聊天流" in r["content"]
