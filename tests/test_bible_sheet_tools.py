import asyncio
import types


class FakeRender:
    async def html2png(self, html, viewport=None, **kw):
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
    inst._ctx = types.SimpleNamespace(send=FakeSend(), render=FakeRender(), logger=FakeLogger())
    cfg = plugin.MaiTRPGConfig()
    cfg.storage.data_dir = str(tmp_path)
    inst._plugin_config_instance = cfg
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
