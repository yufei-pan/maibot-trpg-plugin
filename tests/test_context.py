from trpg_batch import Entry
from trpg_context import assemble_messages, bible_block


def test_bible_block_orders_and_skips_empty():
    block = bible_block({"world": "高塔林立", "plot": "", "gm_subprompt": "严厉"})
    assert "## world" in block and "高塔林立" in block
    assert "## plot" not in block  # empty skipped


def test_role_mapping_and_world_state_first():
    msgs = assemble_messages(
        world_state="队伍在城门口",
        recent_turns=[Entry("u1", "human", "我敲门"), Entry("gm", "gm", "门开了")],
        batch=[Entry("mai", "maibot", "我跟上")],
        char_budget=10_000,
    )
    assert msgs[0]["role"] == "user" and "当前局势" in msgs[0]["content"]
    assert msgs[1] == {"role": "user", "content": "「u1」我敲门"}
    assert msgs[2] == {"role": "assistant", "content": "门开了"}
    assert msgs[-1] == {"role": "user", "content": "「mai」我跟上"}


def test_budget_drops_oldest_recent_but_keeps_batch():
    recent = [Entry(f"u{i}", "human", "X" * 100) for i in range(50)]
    batch = [Entry("u1", "human", "关键行动")]
    msgs = assemble_messages(world_state="W", recent_turns=recent, batch=batch, char_budget=500)
    joined = "".join(m["content"] for m in msgs)
    assert "关键行动" in joined          # batch preserved
    assert "当前局势" in msgs[0]["content"]  # world_state preserved
    assert len(joined) <= 500 + 200      # roughly within budget (allow prefixes)
