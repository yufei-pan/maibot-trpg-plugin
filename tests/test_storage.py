from pathlib import Path

from trpg_storage import Paths, append_line, list_sessions, read_toml, safe_stream_dir, write_toml


def test_safe_stream_dir_sanitizes_and_is_stable():
    assert safe_stream_dir("group/123") == "group_123"
    assert safe_stream_dir("").startswith("s_")
    assert safe_stream_dir("group:1") == safe_stream_dir("group:1")


def test_paths_layout(tmp_path):
    p = Paths(tmp_path, "g1", "camp1")
    assert p.session_dir == tmp_path / "g1" / "camp1"
    assert p.bible_file("world.md") == tmp_path / "g1" / "camp1" / "bible" / "world.md"
    assert p.character_toml("u9") == tmp_path / "g1" / "camp1" / "characters" / "u9.toml"


def test_toml_roundtrip_atomic(tmp_path):
    p = tmp_path / "x.toml"
    write_toml(p, {"status": "setup", "members": ["a", "b"]})
    assert read_toml(p) == {"status": "setup", "members": ["a", "b"]}
    assert read_toml(tmp_path / "missing.toml") == {}


def test_append_line_and_list_sessions(tmp_path):
    p = Paths(tmp_path, "g1", "camp1")
    append_line(p.audit_log, "roll u1 d20=14")
    assert p.audit_log.read_text(encoding="utf-8") == "roll u1 d20=14\n"
    write_toml(p.session_toml, {"session_id": "camp1", "status": "setup", "members": [], "title": "无标题"})
    sessions = list_sessions(tmp_path, "g1")
    assert sessions == [{"session_id": "camp1", "status": "setup", "members": [], "title": "无标题"}]
