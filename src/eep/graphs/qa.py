"""G4 qa_graph: experience Q&A / chain explanation with forced citations.

Flow:
  route -> hybrid_retrieve -> answer_with_citations (every conclusion must
  carry meeting_id + span) -> record_query_memory (user focus -> procedural
  memory via LangMem, Phase 2).

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import json
import logging
import re
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from eep.ai_providers.llm_log import invoke_llm

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
    semaphores: Any                 # ProviderSemaphores (injected by the API layer)


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


def _grounded_fallback(hits: list[dict[str, Any]]) -> str:
    """Deterministic bullet answer; used when no LLM is available or it fails."""
    return "\n".join(f"- {h.get('title', '')}" for h in hits) if hits else (
        "No relevant experience found in the library."
    )


async def answer_with_citations(state: QAState) -> dict[str, Any]:
    """Answer grounded ONLY in retrieved hits; each claim cites meeting+span.

    The LLM (role='summarizer') composes a readable answer from the hit list
    but must not introduce facts; citations are always derived from the hits
    themselves. Any LLM failure falls back to the bullet list.
    """
    hits = state.get("hits", [])
    citations: list[dict[str, Any]] = [
        {
            "meeting_id": h.get("source_meeting_id"),
            "span": h.get("source_span", {}),
        }
        for h in hits
    ]

    factory = state.get("factory")
    sems = state.get("semaphores")
    if factory is None or sems is None or not hits:  # tests / bare invocation / no evidence
        return {"answer": _grounded_fallback(hits), "citations": citations}

    try:
        llm = factory.get_chat_model("summarizer")
        context = [
            {
                "title": h.get("title", ""),
                "description": h.get("description", ""),
                "meeting_id": h.get("source_meeting_id"),
                "span": h.get("source_span", {}),
            }
            for h in hits
        ]

        async def _call() -> str:
            messages = [
                (
                    "system",
                    "You answer questions strictly from the provided experience "
                    "library hits. Never add facts beyond them. Reference each "
                    "claim with its meeting_id (cite as [meeting <id>]).",
                ),
                (
                    "user",
                    f"Question: {state.get('question', '')}\n\n"
                    f"Hits:\n{json.dumps(context, ensure_ascii=False, default=str)}",
                ),
            ]
            resp = await invoke_llm("qa.answer_with_citations", "summarizer", llm, messages)
            return str(resp.content)

        raw = await sems.run("lmstudio-local", _call)
        answer = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE).strip()
        return {"answer": answer or _grounded_fallback(hits), "citations": citations}
    except Exception:  # noqa: BLE001 - Q&A must degrade, not fail
        logger.exception("LLM QA answer failed; using grounded bullet list")
        return {"answer": _grounded_fallback(hits), "citations": citations}


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
