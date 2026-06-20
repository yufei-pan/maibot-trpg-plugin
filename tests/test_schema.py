from trpg_schema import (DEFAULT_SCHEMA, apply_edits, blank_sheet, resolve_schema,
                         sheet_complete, validate_sheet)


def test_resolve_default_when_none():
    s = resolve_schema(None)
    keys = {f["key"] for f in s["fields"]}
    assert {"name", "hp", "ac", "str_", "inventory"} <= keys
    s["fields"].append({"key": "x"})
    assert len(resolve_schema(None)["fields"]) == len(DEFAULT_SCHEMA["fields"])  # no shared mutation


def test_semi_custom_add_modify_remove():
    s = apply_edits(resolve_schema(None),
                    add=[{"key": "sanity", "label": "理智", "type": "int", "default": 100, "required": True}],
                    modify=[{"key": "hp", "default": 20}],
                    remove=["cha"])
    by = {f["key"]: f for f in s["fields"]}
    assert by["sanity"]["default"] == 100
    assert by["hp"]["default"] == 20
    assert "cha" not in by


def test_fully_custom_replace():
    custom = {"fields": [{"key": "grit", "label": "胆识", "type": "int", "default": 3, "required": True}]}
    assert resolve_schema(custom) == custom


def test_validate_and_complete():
    s = resolve_schema(None)
    blank = blank_sheet(s)
    # blank has name="" -> required name missing
    problems = validate_sheet(blank, s)
    assert any("name" in p for p in problems)
    blank["name"] = "阿强"
    assert sheet_complete(blank, s)
    blank["hp"] = "ten"  # wrong type
    assert not sheet_complete(blank, s)
