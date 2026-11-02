"""G2 review graph tests: human gate, routing, interrupt/resume lifecycle.

Author: Wang, Bing <colin2wang@gmail.com>
"""

import pytest

from eep.graphs.review import _route_outcome, build_review_graph, suggest_edits


# ------------------------------------------------------------------ #
# Node logic
# ------------------------------------------------------------------ #
async def test_suggest_edits_flags_missing_quote_and_owner() -> None:
    draft = {"type": "action", "source": {"span": {}}, "owner_hint": None}
    state = await suggest_edits({"draft": draft})
    assert len(state["suggestions"]) == 2


async def test_suggest_edits_clean_draft_no_suggestions() -> None:
    draft = {
        "type": "action",
        "owner_hint": "黄滔",
        "source": {"span": {"quote": "原文"}},
    }
    state = await suggest_edits({"draft": draft})
    assert state["suggestions"] == []


def test_route_outcome_accept_and_reject() -> None:
    assert _route_outcome({"decision": {"decision": "accept"}}) == "promote"
    assert _route_outcome({"decision": {"decision": "accept_edited"}}) == "promote"
    assert _route_outcome({"decision": {"decision": "reject", "reason": "幻觉"}}) == "reject"
    assert _route_outcome({"outcome": "failed", "decision": {"decision": "reject"}}) == "failed"


# ------------------------------------------------------------------ #
# Graph assembly + interrupt lifecycle
# ------------------------------------------------------------------ #
def test_review_graph_compiles() -> None:
    assert build_review_graph().compile() is not None


@pytest.mark.filterwarnings("ignore")
async def test_review_graph_interrupts_then_resumes_to_promote() -> None:
    """The G2 human gate: run suspends at interrupt(); resume promotes."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command

    graph = build_review_graph().compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t-review-1"}}
    draft = {
        "type": "action",
        "title": "跟进审批",
        "owner_hint": "黄滔",
        "source": {"span": {"start": 0, "end": 4, "quote": "跟进授权审批进度"}},
    }
    result = await graph.ainvoke({"draft": draft, "similar": []}, config=config)
    # Suspended at human_review: no outcome yet.
    assert result.get("outcome") is None

    final = await graph.ainvoke(
        Command(resume={"decision": "accept"}), config=config
    )
    assert final["outcome"] == "promoted"


@pytest.mark.filterwarnings("ignore")
async def test_review_graph_reject_requires_reason() -> None:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command

    graph = build_review_graph().compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t-review-2"}}
    draft = {
        "type": "decision",
        "title": "某决策",
        "source": {"span": {"start": 0, "end": 2, "quote": "原文"}},
    }
    await graph.ainvoke({"draft": draft, "similar": []}, config=config)

    # Reject without reason -> outcome "failed" (routing skips both branches).
    failed = await graph.ainvoke(
        Command(resume={"decision": "reject", "reason": None}), config=config
    )
    assert failed["outcome"] == "failed"

    # Reject with reason -> rejected.
    config2 = {"configurable": {"thread_id": "t-review-3"}}
    await graph.ainvoke({"draft": draft, "similar": []}, config=config2)
    rejected = await graph.ainvoke(
        Command(resume={"decision": "reject", "reason": "与库内 decision-102 重复"}), config=config2
    )
    assert rejected["outcome"] == "rejected"
