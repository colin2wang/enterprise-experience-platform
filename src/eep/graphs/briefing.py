"""G3 briefing_graph: pre-meeting briefing composer (read-only).

Flow:
  gather_attention -> parallel Send: retrieve_pilots / retrieve_decision_quotes
  / retrieve_open_actions -> compose_briefing (every item carries a source
  link) -> export_docx/pdf placeholder.

LLM only organizes and compresses; adding new facts is forbidden.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)


def _append_unique(current: list[Any], new: list[Any]) -> list[Any]:
    seen = {id(x) for x in current}
    return current + [x for x in new if id(x) not in seen]


class BriefingState(TypedDict, total=False):
    project_id: str
    attention: Annotated[list[dict[str, Any]], _append_unique]
    pilots: Annotated[list[dict[str, Any]], _append_unique]
    decision_quotes: Annotated[list[dict[str, Any]], _append_unique]
    open_actions: Annotated[list[dict[str, Any]], _append_unique]
    briefing_markdown: str
    factory: Any


async def gather_attention(state: BriefingState) -> dict[str, Any]:
    """Attention items = recently updated / pending formal experiences."""
    return {}


def fan_out_retrievals(state: BriefingState) -> list[Any]:
    """Fan out the three read-only retrievals in parallel."""
    return [
        {"task": "pilots", "project_id": state["project_id"]},
        {"task": "decision_quotes", "project_id": state["project_id"]},
        {"task": "open_actions", "project_id": state["project_id"]},
    ]


async def retrieve_pilots(task: dict[str, Any]) -> dict[str, Any]:
    """Experiments with status 'planned' (current pilot scope sidebar)."""
    return {"pilots": []}


async def retrieve_decision_quotes(task: dict[str, Any]) -> dict[str, Any]:
    """Effective decisions, each with meeting_id + span citation."""
    return {"decision_quotes": []}


async def retrieve_open_actions(task: dict[str, Any]) -> dict[str, Any]:
    """Actions not completed, with owner/due info for the follow-up section."""
    return {"open_actions": []}


async def compose_briefing(state: BriefingState) -> dict[str, Any]:
    """Render the briefing template; pure deterministic composition.

    Every line links back to its source meeting. LLM compression is optional
    and never introduces facts; Phase 1 uses the template directly.
    """
    lines: list[str] = ["# Pre-meeting briefing", ""]
    lines.append("## Needs confirmation this time")
    for item in state.get("attention", []):
        src = item.get("source_meeting_id", "")
        lines.append(f"- [{item.get('code', '')}] {item.get('title', '')} (source: {src})")
    lines.append("")
    lines.append("## Effective decisions (traceable)")
    for q in state.get("decision_quotes", []):
        span = q.get("source_span", {})
        lines.append(f"- {q.get('title', '')} — meeting {q.get('source_meeting_id', '')} span {span}")
    lines.append("")
    lines.append("## Open actions")
    for a in state.get("open_actions", []):
        due = a.get("due_date") or "TBD"
        lines.append(f"- {a.get('title', '')} — owner {a.get('owner_name') or 'unclaimed'}, due {due}")
    return {"briefing_markdown": "\n".join(lines)}


async def export_doc(state: BriefingState) -> dict[str, Any]:
    """Export hook (docx/pdf). Phase 1 returns markdown; conversion is a P1 job."""
    logger.info("Briefing composed: %d chars", len(state.get("briefing_markdown", "")))
    return {}


def build_briefing_graph() -> StateGraph:
    """Build the G3 briefing graph."""
    g = StateGraph(BriefingState)
    g.add_node("gather_attention", gather_attention)
    g.add_node("retrieve_pilots", retrieve_pilots)
    g.add_node("retrieve_decision_quotes", retrieve_decision_quotes)
    g.add_node("retrieve_open_actions", retrieve_open_actions)
    g.add_node("compose_briefing", compose_briefing)
    g.add_node("export_doc", export_doc)

    g.add_edge(START, "gather_attention")
    g.add_edge("gather_attention", "retrieve_pilots")
    g.add_edge("gather_attention", "retrieve_decision_quotes")
    g.add_edge("gather_attention", "retrieve_open_actions")
    g.add_edge("retrieve_pilots", "compose_briefing")
    g.add_edge("retrieve_decision_quotes", "compose_briefing")
    g.add_edge("retrieve_open_actions", "compose_briefing")
    g.add_edge("compose_briefing", "export_doc")
    g.add_edge("export_doc", END)
    return g
