"""G2 review graph: human-in-the-loop extraction review via interrupt().

Pipeline:
    load_draft -> retrieve_similar -> suggest_edits
      -> interrupt(human verdict)
      -> apply_decision -> promote | reject -> finalize_meeting

The review queue is the list of threads currently suspended in interrupt();
progress survives restarts via PostgresSaver checkpoints.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from eep.ai_providers.llm_log import invoke_llm
from eep.schemas import ReviewSubmit

logger = logging.getLogger(__name__)


class ReviewState(TypedDict, total=False):
    """Working memory of one review thread."""

    thread_id: str
    meeting_id: str
    project_id: str
    draft: dict[str, Any]           # candidate experience awaiting verdict
    similar: list[dict[str, Any]]   # formal-layer neighbors shown to the reviewer
    suggestions: list[str]
    suggestions_from_store: bool    # suggestions loaded from Extraction.draft_json
    decision: dict[str, Any]        # ReviewSubmit payload from the reviewer
    outcome: str                    # promoted | rejected | failed
    change_log: list[dict[str, Any]]
    factory: Any                    # ModelFactory (injected by the API layer)
    semaphores: Any                 # ProviderSemaphores (injected by the API layer)


# --------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------- #
async def load_draft(state: ReviewState) -> dict[str, Any]:
    """Load the draft candidate (injected by the API layer at invoke time)."""
    return {}


async def retrieve_similar(state: ReviewState) -> dict[str, Any]:
    """Recall formal-layer neighbors for the reviewer ("what the library has").

    Production path: MemoryService.retrieve (vector + 1-hop edge expansion).
    Here we pass through the drafts' precomputed similar list so the graph
    stays decoupled from a live Postgres; the API layer fills it in.
    """
    return {}


def _rule_suggestions(draft: dict[str, Any]) -> list[str]:
    """Deterministic checks that never require an LLM."""
    suggestions: list[str] = []
    if not draft.get("source", {}).get("span", {}).get("quote"):
        suggestions.append("Missing source quote: verify the span before accepting.")
    if draft.get("type") == "action" and not draft.get("owner_hint"):
        suggestions.append("No owner hint: item will show as 'unclaimed'.")
    return suggestions


def _parse_suggestions(raw: str) -> list[str]:
    """Parse the LLM reply into at most 5 suggestion strings; never raises."""
    try:
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        data = json.loads(text)
        items = data.get("suggestions") if isinstance(data, dict) else data
        return [str(s) for s in items if isinstance(s, str) and s.strip()][:5]
    except Exception:  # noqa: BLE001 - suggestions are advisory only
        return []


async def suggest_edits(state: ReviewState) -> dict[str, Any]:
    """LLM-suggested field fixes (strong model, role='extractor').

    Rule-based checks always run; the LLM adds advisory suggestions on top.
    Suggestions generated on a previous queue visit are persisted in
    ``Extraction.draft_json`` and replayed via ``suggestions_from_store`` —
    the LLM is called at most once per draft. Any LLM failure degrades
    gracefully to rules-only output. Suggestions are advisory only; the
    reviewer makes the final call.
    """
    draft = state.get("draft", {})
    if state.get("suggestions_from_store"):
        # Already contains rule-based + LLM suggestions from the first run.
        return {"suggestions": state.get("suggestions", [])}

    suggestions = _rule_suggestions(draft)

    factory = state.get("factory")
    sems = state.get("semaphores")
    if factory is None or sems is None:  # tests / bare invocation
        return {"suggestions": suggestions}

    try:
        llm = factory.get_chat_model("extractor")

        async def _call() -> str:
            messages = [
                (
                    "system",
                    "You review a draft experience-unit before human acceptance. "
                    "Point out concrete field-level problems only (title clarity, "
                    "type mismatch, missing span evidence, risky wording). "
                    "Never invent facts. Return JSON: {\"suggestions\": [\"...\"]}. "
                    "Return an empty list when the draft looks fine.",
                ),
                ("user", json.dumps(draft, ensure_ascii=False, default=str)),
            ]
            resp = await invoke_llm("review.suggest_edits", "extractor", llm, messages)
            return str(resp.content)

        raw = await sems.run("lmstudio-local", _call)
        suggestions.extend(s for s in _parse_suggestions(raw) if s not in suggestions)
    except Exception:  # noqa: BLE001 - advisory feature must not break review
        logger.exception("LLM suggestion failed for draft review; keeping rule-based only")

    return {"suggestions": suggestions}


async def human_review(state: ReviewState) -> dict[str, Any]:
    """Suspend until the reviewer submits a verdict via the workbench."""
    decision_raw = interrupt(
        {
            "draft": state["draft"],
            "similar": state.get("similar", []),
            "suggestions": state.get("suggestions", []),
            "source_span": state.get("draft", {}).get("source", {}).get("span"),
        }
    )
    decision = ReviewSubmit.model_validate(decision_raw)
    return {"decision": decision.model_dump(mode="json")}


async def apply_decision(state: ReviewState) -> dict[str, Any]:
    """Route on the verdict; validate that reject carries a reason."""
    decision = state["decision"]
    if decision["decision"] == "reject" and not decision.get("reason"):
        return {"outcome": "failed"}
    return {}


def _route_outcome(state: ReviewState) -> str:
    if state.get("outcome") == "failed":
        return "failed"  # reject without a reason: stop, do not reject
    d = state["decision"]["decision"]
    return "promote" if d in ("accept", "accept_edited") else "reject"


async def promote(state: ReviewState) -> dict[str, Any]:
    """Promote draft to the formal layer (DB writes done by the API layer).

    Transaction on resume: experience insert + change_log + draft marked
    promoted; confidence set to 1 (human-verified).
    """
    return {"outcome": "promoted"}


async def reject(state: ReviewState) -> dict[str, Any]:
    """Reject the draft; archived after 90 days by the retention job."""
    return {"outcome": "rejected"}


async def finalize_meeting(state: ReviewState) -> dict[str, Any]:
    """No-op marker node; the API layer flips the meeting to 'reviewed'."""
    return {}


# --------------------------------------------------------------------- #
# Graph assembly
# --------------------------------------------------------------------- #
def build_review_graph() -> StateGraph:
    """Build the G2 review graph with an interrupt-based human gate."""
    g = StateGraph(ReviewState)
    g.add_node("load_draft", load_draft)
    g.add_node("retrieve_similar", retrieve_similar)
    g.add_node("suggest_edits", suggest_edits)
    g.add_node("human_review", human_review)
    g.add_node("apply_decision", apply_decision)
    g.add_node("promote", promote)
    g.add_node("reject", reject)
    g.add_node("finalize_meeting", finalize_meeting)

    g.add_edge(START, "load_draft")
    g.add_edge("load_draft", "retrieve_similar")
    g.add_edge("retrieve_similar", "suggest_edits")
    g.add_edge("suggest_edits", "human_review")
    g.add_edge("human_review", "apply_decision")
    g.add_conditional_edges(
        "apply_decision",
        _route_outcome,
        {"promote": "promote", "reject": "reject", "failed": END},
    )
    g.add_edge("promote", "finalize_meeting")
    g.add_edge("reject", "finalize_meeting")
    g.add_edge("finalize_meeting", END)
    return g
