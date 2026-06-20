"""MaiTRPG 配置模型测试。"""

from __future__ import annotations


def test_config_defaults():
    import plugin
    inst = plugin.create_plugin()
    cfg = plugin.MaiTRPGConfig()
    assert cfg.plugin.maibot_plays is True
    assert cfg.gm.main_gm_prompt.strip()           # ships a default zh-CN GM prompt
    assert cfg.loop.inactivity_flush_seconds >= 5
    assert cfg.loop.ooc_marker == "/ooc"
    assert cfg.context.char_budget >= 10000


def test_data_root_defaults_to_plugin_data(tmp_path, monkeypatch):
    import plugin
    inst = plugin.create_plugin()
    inst._plugin_config_instance = plugin.MaiTRPGConfig()
    root = inst._data_root()
    assert root.name == "data"
