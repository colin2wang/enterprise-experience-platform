"""G4 qa graph tests: routing and forced meeting+span citations.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from eep.graphs.qa import answer_with_citations, build_qa_graph, route


async def test_route_chain_explain_by_keyword() -> None:
    assert (await route({"question": "解释一下这条经验的 chain"}))["route"] == "chain_explain"
    assert (await route({"question": "试点场景是什么"}))["route"] == "answer"


async def test_answer_with_citations_forces_meeting_span() -> None:
    state = await answer_with_citations(
        {
            "hits": [
                {"title": "决策一", "source_meeting_id": "m-1", "source_span": {"start": 0, "end": 3}},
                {"title": "决策二", "source_meeting_id": "m-2", "source_span": {}},
            ]
        }
    )
    assert len(state["citations"]) == 2
    assert state["citations"][0] == {"meeting_id": "m-1", "span": {"start": 0, "end": 3}}
    assert "决策一" in state["answer"]


async def test_answer_with_no_hits_says_not_found() -> None:
    state = await answer_with_citations({"hits": []})
    assert state["answer"] == "No relevant experience found in the library."
    assert state["citations"] == []


def test_qa_graph_compiles() -> None:
    assert build_qa_graph().compile() is not None
