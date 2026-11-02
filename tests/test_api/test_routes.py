"""Meeting + overview API route tests (in-memory SQLite; handlers called directly).

Author: Wang, Bing <colin2wang@gmail.com>
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from eep.api.routes import list_meetings, meeting_detail, overview


async def test_list_meetings_returns_five_newest_first(session, pid) -> None:
    meetings = await list_meetings(pid, q=None, sort="-date", session=session)
    assert len(meetings) == 5
    dates = [m.meet_date for m in meetings]
    assert dates == sorted(dates, reverse=True)


async def test_list_meetings_search_keeps_transcript_prefix(session, pid) -> None:
    hits = await list_meetings(pid, q="场景优先级", sort="-date", session=session)
    assert len(hits) == 1
    assert hits[0].title.startswith("转写_")
    assert hits[0].review_status == "reviewed"


async def test_meeting_detail_carries_summary_and_related(session, pid) -> None:
    meetings = await list_meetings(pid, q=None, sort="-date", session=session)
    detail = await meeting_detail(meetings[0].id, session=session)
    assert detail.summary
    assert detail.discussion
    assert len(detail.related_experiences) >= 1
    assert all(r.code for r in detail.related_experiences)


async def test_meeting_detail_not_found_raises_404(session) -> None:
    with pytest.raises(HTTPException) as exc:
        await meeting_detail("00000000-0000-0000-0000-000000000001", session=session)
    assert exc.value.status_code == 404


async def test_overview_metrics_match_seed(session, pid) -> None:
    out = await overview(pid, session=session)
    # 16 experiences: 6 effective decisions, 2 open actions (action-110/111/112
    # are in_progress = 3, action-114 pending = 1 → 4 open)
    assert out.metrics["total_experiences"] == 16
    assert out.metrics["total_meetings"] == 5
    assert out.metrics["effective_decisions"] == 6
    assert out.metrics["open_actions"] == 4


async def test_overview_attention_and_pilots(session, pid) -> None:
    out = await overview(pid, session=session)
    assert len(out.attention_list) >= 1  # pending experiences (action-114)
    assert all(item.status == "pending" for item in out.attention_list)
    assert len(out.pilots) == 2  # two planned experiments
    assert all(p.type == "experiment" for p in out.pilots)
    assert len(out.decision_quotes) == 6
    assert all(q.status == "effective" for q in out.decision_quotes)


async def test_overview_unknown_project_is_empty(session) -> None:
    out = await overview("00000000-0000-0000-0000-000000000009", session=session)
    assert out.metrics["total_experiences"] == 0
    assert out.attention_list == []
