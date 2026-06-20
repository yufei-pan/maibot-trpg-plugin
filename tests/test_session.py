from trpg_schema import blank_sheet, resolve_schema
from trpg_session import (READY, RUNNING, SETUP, add_member, mark_card_done, new_session_meta,
                          ready_check, story_held)


def _complete_sheet():
    s = resolve_schema(None)
    sheet = blank_sheet(s)
    sheet["name"] = "英雄"
    return s, sheet


def test_new_session_includes_maibot_member():
    meta = new_session_meta("camp1", "初章", maibot_member="mai")
    assert meta["status"] == SETUP and meta["members"] == ["mai"]


def test_ready_blocks_until_bible_and_cards_complete():
    schema, sheet = _complete_sheet()
    meta = add_member(new_session_meta("c", "t", maibot_member=None), "u1")
    present = {"world": True, "plot": False, "gm_subprompt": True}
    rep = ready_check(meta, bible_present=present, schema=schema, sheets={"u1": sheet})
    assert not rep.ok and any("plot" in m or "剧情" in m for m in rep.missing)

    present["plot"] = True
    rep2 = ready_check(meta, bible_present=present, schema=schema, sheets={"u1": {}})
    assert not rep2.ok and any("u1" in m for m in rep2.missing)

    rep3 = ready_check(meta, bible_present=present, schema=schema, sheets={"u1": sheet})
    assert rep3.ok and rep3.missing == []


def test_story_held_for_pending_card_in_running():
    meta = add_member(new_session_meta("c", "t", maibot_member=None), "u2")
    meta["status"] = RUNNING
    assert story_held(meta)            # u2 still pending
    meta = mark_card_done(meta, "u2")
    assert not story_held(meta)
