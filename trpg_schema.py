"""属性表 schema：支持默认 / 半自定义（增删改字段）/ 全自定义。系统无关、强类型。"""

from __future__ import annotations

import copy
from typing import Any

_PY_TYPES = {"str": str, "int": int, "float": (int, float), "bool": bool, "list": list}

DEFAULT_SCHEMA: dict[str, Any] = {
    "fields": [
        {"key": "name", "label": "姓名", "type": "str", "default": "", "required": True},
        {"key": "level", "label": "等级", "type": "int", "default": 1, "required": False},
        {"key": "hp", "label": "生命值", "type": "int", "default": 10, "required": True},
        {"key": "ac", "label": "护甲", "type": "int", "default": 10, "required": False},
        {"key": "str_", "label": "力量", "type": "int", "default": 10, "required": False},
        {"key": "dex", "label": "敏捷", "type": "int", "default": 10, "required": False},
        {"key": "con", "label": "体质", "type": "int", "default": 10, "required": False},
        {"key": "int_", "label": "智力", "type": "int", "default": 10, "required": False},
        {"key": "wis", "label": "感知", "type": "int", "default": 10, "required": False},
        {"key": "cha", "label": "魅力", "type": "int", "default": 10, "required": False},
        {"key": "inventory", "label": "物品", "type": "list", "default": [], "required": False},
        {"key": "conditions", "label": "状态", "type": "list", "default": [], "required": False},
        {"key": "notes", "label": "备注", "type": "str", "default": "", "required": False},
    ]
}


def resolve_schema(custom: dict[str, Any] | None) -> dict[str, Any]:
    if not custom or not custom.get("fields"):
        return copy.deepcopy(DEFAULT_SCHEMA)
    for f in custom["fields"]:
        if not f.get("key") or f.get("type") not in _PY_TYPES:
            raise ValueError(f"自定义 schema 字段非法（需有 key 与合法 type）：{f!r}")
    return copy.deepcopy(custom)


def apply_edits(schema: dict[str, Any], *, add: list[dict] = (), modify: list[dict] = (),
                remove: list[str] = ()) -> dict[str, Any]:
    fields = [copy.deepcopy(f) for f in schema["fields"]]
    by_key = {f["key"]: f for f in fields}
    for patch in modify:
        key = patch.get("key")
        if key in by_key:
            if "type" in patch and patch["type"] not in _PY_TYPES:
                raise ValueError(f"修改字段 type 非法：{patch!r}")
            by_key[key].update({k: v for k, v in patch.items() if k != "key"})
    rm = set(remove)
    fields = [f for f in fields if f["key"] not in rm]
    existing = {f["key"] for f in fields}
    for f in add:
        if f.get("key") and f["key"] not in existing:
            if f.get("type") not in _PY_TYPES:
                raise ValueError(f"新增字段 type 非法：{f!r}")
            fields.append(copy.deepcopy(f))
    return {"fields": fields}


def field_types(schema: dict[str, Any]) -> dict[str, str]:
    return {f["key"]: f["type"] for f in schema["fields"]}


def blank_sheet(schema: dict[str, Any]) -> dict[str, Any]:
    return {f["key"]: copy.deepcopy(f.get("default")) for f in schema["fields"]}


def validate_sheet(sheet: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for f in schema["fields"]:
        key, typ, label = f["key"], f["type"], f.get("label", f["key"])
        val = sheet.get(key, None)
        if f.get("required"):
            if val is None or (isinstance(val, str) and not val.strip()) or val == []:
                problems.append(f"缺少必填字段 {label}（{key}）")
                continue
        if val is not None and not isinstance(val, _PY_TYPES[typ]):
            problems.append(f"字段 {label}（{key}）类型应为 {typ}")
    return problems


def sheet_complete(sheet: dict[str, Any], schema: dict[str, Any]) -> bool:
    return validate_sheet(sheet, schema) == []
