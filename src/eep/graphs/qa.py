"""G4 qa_graph: experience Q&A / chain explanation with forced citations.

Flow:
  route -> hybrid_retrieve -> answer_with_citations (every conclusion must
  carry meeting_id + span) -> record_query_memory (user focus -> procedural
  memory via LangMem, Phase 2).

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


class QAState(TypedDict, total=False):
    project_id: str
    question: str
    route: str                      # answer | chain_explain
    hits: Annotated[list[dict[str, Any]], _append_unique]
    answer: str
    citations: list[dict[str, Any]]
    factory: Any


async def route(state: QAState) -> dict[str, Any]:
    """Keyword routing; chain explanation when the question names an experience."""
    q = state.get("question", "")
    route = "chain_explain" if "chain" in q or "evolution" in q else "answer"
    return {"route": route}


async def hybrid_retrieve(state: QAState) -> dict[str, Any]:
    """Hybrid retrieval (hard filter -> pgvector -> 1-hop edges -> rerank).

    Delegates to MemoryService.retrieve, injected by the API layer; the node
    stays a thin adapter so the graph is testable without a live DB.
    """
    return {}


async def answer_with_citations(state: QAState) -> dict[str, Any]:
    """Answer grounded ONLY in retrieved hits; each claim cites meeting+span."""
    hits = state.get("hits", [])
    lines: list[str] = []
    citations: list[dict[str, Any]] = []
    for h in hits:
        lines.append(f"- {h.get('title', '')}")
        citations.append(
            {
                "meeting_id": h.get("source_meeting_id"),
                "span": h.get("source_span", {}),
            }
        )
    answer = "\n".join(lines) if lines else "No relevant experience found in the library."
    return {"answer": answer, "citations": citations}


async def record_query_memory(state: QAState) -> dict[str, Any]:
    """Record the user's focus into procedural memory (LangMem, Phase 2)."""
    return {}


def build_qa_graph() -> StateGraph:
    """Build the G4 QA graph."""
    g = StateGraph(QAState)
    g.add_node("route", route)
    g.add_node("hybrid_retrieve", hybrid_retrieve)
    g.add_node("answer_with_citations", answer_with_citations)
    g.add_node("record_query_memory", record_query_memory)

    g.add_edge(START, "route")
    g.add_edge("route", "hybrid_retrieve")
    g.add_edge("hybrid_retrieve", "answer_with_citations")
    g.add_edge("answer_with_citations", "record_query_memory")
    g.add_edge("record_query_memory", END)
    return g
