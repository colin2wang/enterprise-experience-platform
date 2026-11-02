"""G1 ingestion_graph: meeting ingestion pipeline.

Flow:
  fetch_meeting -> transcribe -> summarize -> chunk_split
    -> Send parallel: extract_experiences xN -> merge_drafts
    -> dedupe_and_link -> write_draft_memory -> notify_review

AI writes only to the draft layer (pending review), never directly to the
formal experience library.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from eep.ai_providers import ModelFactory, ProviderSemaphores
from eep.ai_providers.llm_log import invoke_llm
from eep.graphs.extraction_prompt import (
    EXTRACT_SYSTEM_PROMPT,
    build_extract_user_prompt,
    parse_extraction_text,
)
from eep.schemas import ExtractedItem

logger = logging.getLogger(__name__)

CHUNK_SIZE = 3000
CHUNK_OVERLAP = 200


def _append_unique(current: list[Any], new: list[Any]) -> list[Any]:
    """Annotated reducer: merge lists without duplicates by identity."""
    seen = {id(x) for x in current}
    return current + [x for x in new if id(x) not in seen]


class IngestionState(TypedDict, total=False):
    """Working memory of one ingestion run."""

    project_id: str
    meeting_id: str
    transcript: str
    summary: str
    discussion: str
    chunks: list[dict[str, Any]]
    drafts: Annotated[list[dict[str, Any]], _append_unique]
    relations: list[dict[str, Any]]
    errors: Annotated[list[str], _append_unique]
    semaphores: Any  # ProviderSemaphores
    factory: Any  # ModelFactory


# --------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------- #
def _parse_summary_reply(raw: str) -> dict[str, str] | None:
    """Parse the summarizer reply as ``{"summary", "discussion"}``.

    The summarizer does NOT follow the extraction schema, so it must not go
    through ``parse_extraction_text`` — that would validate against
    ``ExtractionOutput`` and silently yield empty items (and therefore empty
    summary/discussion) for a perfectly good reply.
    """
    text = raw.strip()
    if text.startswith("```"):  # strip Markdown code fences
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    summary = str(data.get("summary") or "").strip()
    discussion = str(data.get("discussion") or "").strip()
    if not summary and not discussion:
        return None
    return {"summary": summary, "discussion": discussion}


async def summarize(state: IngestionState) -> dict[str, Any]:
    """Summarize the transcript into Summary/Discussion structure (light model)."""
    factory: ModelFactory = state["factory"]
    sems: ProviderSemaphores = state["semaphores"]
    llm = factory.get_chat_model("summarizer")

    async def _call() -> str:
        messages = (
            "Split the meeting transcript below into two sections.\n"
            'Return JSON: {"summary": "...", "discussion": "..."}\n\n'
            f"Transcript:\n{state['transcript'][:12000]}"
        )
        resp = await invoke_llm("ingestion.summarize", "summarizer", llm, messages)
        return str(resp.content)

    raw = await sems.run("ollama-local", _call)
    parsed = _parse_summary_reply(raw)
    if parsed is None:
        return {"errors": ["summarize: unparseable LLM output"]}
    return {"summary": parsed["summary"], "discussion": parsed["discussion"]}


def chunk_split(state: IngestionState) -> dict[str, Any]:
    """Split the transcript into overlapping chunks for parallel extraction."""
    text = state["transcript"]
    chunks: list[dict[str, Any]] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append({"start": start, "end": end, "text": text[start:end]})
        if end == len(text):
            break
        start = end - CHUNK_OVERLAP
    return {"chunks": chunks}


def fan_out_chunks(state: IngestionState) -> list[Send]:
    """Dynamic parallelism: one extract_experiences task per chunk."""
    return [Send("extract_experiences", {"chunk": c, **_shared(state)}) for c in state["chunks"]]


def _shared(state: IngestionState) -> dict[str, Any]:
    """Fields every Send task needs (factory/semaphores are not picklable refs)."""
    return {"factory": state["factory"], "semaphores": state["semaphores"]}


async def extract_experiences(task_state: dict[str, Any]) -> dict[str, Any]:
    """Extract structured experience candidates from one chunk (strong model).

    MUST emit source_span for every item. Parse failure counts as extraction
    failure (L4) and is recorded as an error for manual entry.
    """
    chunk: dict[str, Any] = task_state["chunk"]
    factory: ModelFactory = task_state["factory"]
    sems: ProviderSemaphores = task_state["semaphores"]
    llm = factory.get_chat_model("extractor")

    async def _call() -> str:
        messages = [
            ("system", EXTRACT_SYSTEM_PROMPT),
            ("user", build_extract_user_prompt(chunk["text"], similar="")),
        ]
        resp = await invoke_llm("ingestion.extract_experiences", "extractor", llm, messages)
        return str(resp.content)

    raw = await sems.run("lmstudio-local", _call)
    parsed = parse_extraction_text(raw, chunk=chunk["text"])
    if parsed is None:
        return {"errors": [f"extract_experiences(chunk@{chunk['start']}): parse failed"]}
    drafts: list[dict[str, Any]] = []
    for item in parsed.items:
        drafts.append(_to_draft(item, chunk))
    return {"drafts": drafts}


def _to_draft(item: ExtractedItem, chunk: dict[str, Any]) -> dict[str, Any]:
    """Shape one extracted item into a draft-memory value (5.4 structure)."""
    return {
        "kind": "experience_draft",
        "type": item.type,
        "title": item.title,
        "description": item.description,
        "owner_hint": item.owner_hint,
        "due_hint": item.due_hint,
        "acceptance_criteria": item.acceptance_criteria,
        "confidence": item.confidence,
        "source": {"span": item.source_span.model_dump(), "chunk_start": chunk["start"]},
        "review_status": "pending",
    }


async def merge_drafts(state: IngestionState) -> dict[str, Any]:
    """Merge per-chunk drafts; drop overlaps duplicated across chunk windows."""
    seen_titles: set[str] = set()
    unique: list[dict[str, Any]] = []
    for d in state.get("drafts", []):
        key = d["title"].strip().lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        unique.append(d)
    return {"drafts": unique}


async def dedupe_and_link(state: IngestionState) -> dict[str, Any]:
    """Vector similarity + entity alignment -> suspected-duplicate relations.

    Phase 1 implementation: exact/near title matching within this run.
    Production path (5.5): pgvector recall >0.92 clustering, relations written
    to the edge table with origin='AI'.
    """
    drafts = state.get("drafts", [])
    relations: list[dict[str, Any]] = []
    for i, a in enumerate(drafts):
        for b in drafts[i + 1 :]:
            score = _title_similarity(a["title"], b["title"])
            if score >= 0.92:
                relations.append(
                    {
                        "from_title": a["title"],
                        "to_title": b["title"],
                        "rel_type": "suspected_duplicate",
                        "origin": "AI",
                        "confidence": score,
                    }
                )
    return {"relations": relations}


def _title_similarity(a: str, b: str) -> float:
    """Cheap Jaccard similarity over character bigrams (Phase 1 stand-in)."""
    ga = {a[i : i + 2] for i in range(max(len(a) - 1, 0))}
    gb = {b[i : i + 2] for i in range(max(len(b) - 1, 0))}
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


async def write_draft_memory(state: IngestionState) -> dict[str, Any]:
    """Persist drafts to the Store draft namespace (status=pending review).

    The Store instance is injected at graph invocation time via config;
    here we mark drafts as written and let the API layer do the put() so the
    graph stays testable without a live Postgres.
    """
    logger.info(
        "G1 run for meeting %s produced %d drafts, %d relations",
        state.get("meeting_id"),
        len(state.get("drafts", [])),
        len(state.get("relations", [])),
    )
    return {}


async def notify_review(state: IngestionState) -> dict[str, Any]:
    """Hand off to the review queue; the API layer starts G2 threads per draft."""
    return {}


# --------------------------------------------------------------------- #
# Graph assembly
# --------------------------------------------------------------------- #
def build_ingestion_graph() -> StateGraph:
    """Build the G1 ingestion graph."""
    g = StateGraph(IngestionState)
    g.add_node("summarize", summarize)
    g.add_node("chunk_split", chunk_split)
    g.add_node("extract_experiences", extract_experiences)
    g.add_node("merge_drafts", merge_drafts)
    g.add_node("dedupe_and_link", dedupe_and_link)
    g.add_node("write_draft_memory", write_draft_memory)
    g.add_node("notify_review", notify_review)

    g.add_edge(START, "summarize")
    g.add_edge("summarize", "chunk_split")
    g.add_conditional_edges("chunk_split", fan_out_chunks, ["extract_experiences"])
    g.add_edge("extract_experiences", "merge_drafts")
    g.add_edge("merge_drafts", "dedupe_and_link")
    g.add_edge("dedupe_and_link", "write_draft_memory")
    g.add_edge("write_draft_memory", "notify_review")
    g.add_edge("notify_review", END)
    return g
