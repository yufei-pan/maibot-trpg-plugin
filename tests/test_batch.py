from trpg_batch import (AdvanceDecision, BatchBuffer, Entry, clean_action, decide_advance,
                        is_ooc)


def test_ooc_detection():
    assert is_ooc("/ooc 等下我去倒水", "/ooc")
    assert is_ooc("(( brb ))", "/ooc")
    assert not is_ooc("我拔出长剑", "/ooc")


def test_clean_action_strips_prefix():
    assert clean_action("/do 撬锁", "/ooc") == "撬锁"
    assert clean_action("/say 站住！", "/ooc") == "站住！"
    assert clean_action("我环顾四周", "/ooc") == "我环顾四周"


def test_buffer_drain_and_has_human():
    b = BatchBuffer()
    b.add(Entry("mai", "maibot", "我点头"))
    assert not b.has_human()
    b.add(Entry("u1", "human", "我开门"))
    assert b.has_human()
    drained = b.drain()
    assert [e.author for e in drained] == ["mai", "u1"]
    assert b.entries == []


def test_runaway_guard():
    empty = BatchBuffer()
    assert decide_advance(empty, 0, 2).advance is False

    human = BatchBuffer(); human.add(Entry("u1", "human", "x"))
    assert decide_advance(human, 5, 2).advance is True  # human always advances

    only_mai = BatchBuffer(); only_mai.add(Entry("mai", "maibot", "x"))
    assert decide_advance(only_mai, 1, 2).advance is True   # under cap
    assert decide_advance(only_mai, 2, 2).advance is False  # cap reached, no human
