"""G3 briefing graph tests: read-only composition with forced source links.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from eep.graphs.briefing import build_briefing_graph, compose_briefing, fan_out_retrievals


def test_fan_out_retrievals_three_tasks() -> None:
    tasks = fan_out_retrievals({"project_id": "p1"})
    assert [t["task"] for t in tasks] == ["pilots", "decision_quotes", "open_actions"]


async def test_compose_briefing_every_line_has_source() -> None:
    state = await compose_briefing(
        {
            "attention": [{"code": "action-114", "title": "跟进审批", "source_meeting_id": "m-9"}],
            "decision_quotes": [
                {"title": "试点场景确认", "source_meeting_id": "m-2", "source_span": {"start": 0, "end": 5}}
            ],
            "open_actions": [{"title": "整理台账", "owner_name": "黄滔", "due_date": None}],
        }
    )
    md = state["briefing_markdown"]
    assert "(source: m-9)" in md
    assert "span {'start': 0, 'end': 5}" in md
    assert "unclaimed" not in md  # owner present
    assert "due TBD" in md  # missing due date falls back to TBD


def test_briefing_graph_compiles() -> None:
    assert build_briefing_graph().compile() is not None
