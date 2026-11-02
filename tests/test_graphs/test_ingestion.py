"""G1 ingestion graph tests (no live LLM / DB needed).

Author: Wang, Bing <colin2wang@gmail.com>
"""

from langgraph.types import Send

from eep.graphs.ingestion import (
    _title_similarity,
    build_ingestion_graph,
    chunk_split,
    dedupe_and_link,
    fan_out_chunks,
    merge_drafts,
)


# ------------------------------------------------------------------ #
# Chunking / fan-out
# ------------------------------------------------------------------ #
def test_chunk_split_produces_overlapping_chunks() -> None:
    text = "x" * (3000 + 2900)  # 5900 chars -> chunk, chunk, remainder
    state = chunk_split({"transcript": text})
    chunks = state["chunks"]
    assert len(chunks) == 3
    # overlap: each later chunk starts before the previous one ends
    assert chunks[1]["start"] < chunks[0]["end"]
    assert chunks[2]["start"] < chunks[1]["end"]
    # reassembling chunks covers the full transcript
    assert chunks[0]["end"] - chunks[0]["start"] == 3000


def test_chunk_split_short_text_single_chunk() -> None:
    state = chunk_split({"transcript": "short meeting"})
    assert len(state["chunks"]) == 1
    assert state["chunks"][0]["text"] == "short meeting"


def test_fan_out_chunks_one_send_per_chunk() -> None:
    sends = fan_out_chunks(
        {"chunks": [{"start": 0, "end": 1, "text": "a"}], "factory": 1, "semaphores": 2}
    )
    assert len(sends) == 1
    assert isinstance(sends[0], Send)
    assert sends[0].node == "extract_experiences"


# ------------------------------------------------------------------ #
# Draft merge + dedupe
# ------------------------------------------------------------------ #
def _draft(title: str, conf: float = 0.9) -> dict:
    return {
        "kind": "experience_draft",
        "type": "decision",
        "title": title,
        "description": "d",
        "owner_hint": None,
        "due_hint": None,
        "acceptance_criteria": None,
        "confidence": conf,
        "source": {"span": {"start": 0, "end": 1, "quote": "q"}, "chunk_start": 0},
        "review_status": "pending",
    }


async def test_merge_drafts_drops_duplicate_titles() -> None:
    state = await merge_drafts({"drafts": [_draft("同一标题"), _draft("同一标题"), _draft("另一条")]})
    titles = [d["title"] for d in state["drafts"]]
    assert titles == ["同一标题", "另一条"]


async def test_dedupe_and_link_flags_near_duplicates() -> None:
    a = "示范项目试点授权审批进度跟进及材料补充事项的确认流程与时间安排全部细节说明"
    b = a[:-1] + "项"  # one trailing char differs -> Jaccard (35/37) >= 0.92
    state = await dedupe_and_link({"drafts": [_draft(a), _draft(b)]})
    assert len(state["relations"]) == 1
    rel = state["relations"][0]
    assert rel["rel_type"] == "suspected_duplicate"
    assert rel["origin"] == "AI"


async def test_dedupe_and_link_ignores_unrelated_titles() -> None:
    state = await dedupe_and_link({"drafts": [_draft("完全不同的话题甲"), _draft("另外一件事情乙")]})
    assert state["relations"] == []


def test_title_similarity_identical_is_one() -> None:
    assert _title_similarity("相同标题", "相同标题") == 1.0
    assert _title_similarity("", "任意") == 0.0


# ------------------------------------------------------------------ #
# Graph assembly
# ------------------------------------------------------------------ #
def test_ingestion_graph_compiles() -> None:
    assert build_ingestion_graph().compile() is not None
