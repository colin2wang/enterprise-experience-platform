"""Extraction prompt + structured-output degradation ladder.

Implements the prompt skeleton from design doc Appendix B and the L1-L4
degradation ladder from chapter 6.4 for local runtimes.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from eep.schemas import ExtractionOutput

logger = logging.getLogger(__name__)

JSON_SCHEMA_HINT = json.dumps(
    {
        "type": "object",
        "required": ["items"],
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["type", "title", "source_span"],
                    "properties": {
                        "type": {
                            "enum": [
                                "question",
                                "hypothesis",
                                "experiment",
                                "decision",
                                "action",
                            ]
                        },
                        "title": {"type": "string", "maxLength": 60},
                        "description": {"type": "string"},
                        "owner_hint": {"type": ["string", "null"]},
                        "due_hint": {"type": ["string", "null"]},
                        "acceptance_criteria": {"type": ["string", "null"]},
                        "source_span": {
                            "type": "object",
                            "properties": {
                                "start": {"type": "integer"},
                                "end": {"type": "integer"},
                                "quote": {"type": "string"},
                            },
                        },
                        "confidence": {"type": "number"},
                    },
                },
            }
        },
    },
    ensure_ascii=False,
)

# Appendix B prompt skeleton, tuned for Qwen2.5/3, in English for consistency.
# The JSON schema is embedded verbatim: local models never saw the pydantic
# contract, so without it they invent their own field names (e.g. "content"
# instead of "title" + "description") and the output fails validation.
EXTRACT_SYSTEM_PROMPT = f"""\
You are an enterprise meeting experience extractor. Extract structured
experience items from the given meeting transcript chunk.
Rules:
1. Extract only items with clear evidence in the chunk; every item MUST include
   a source_span with start/end character positions in the chunk AND the
   verbatim quote copied exactly from the chunk;
2. Five types: question = open question to solve; hypothesis = claim to verify;
   experiment = planned verification activity; decision = a decision already
   made; action = a next step someone must execute;
3. Every item requires a short "title" (max 60 chars) summarizing the point;
   put the full statement into "description";
4. For actions, always try to provide owner_hint and due_hint; if missing, set
   them to null (the UI shows "unclaimed" / "TBD");
5. When uncertain, prefer omitting the item. NEVER fabricate. confidence
   reflects your certainty;
6. Output MUST be a single JSON object exactly matching this schema:

{JSON_SCHEMA_HINT}
"""


def build_extract_user_prompt(chunk: str, similar: str) -> str:
    """Assemble the user message: chunk + similar library context."""
    return f"[Transcript chunk]\n{chunk}\n\n[Context: similar experiences in library, avoid duplicates]\n{similar}"


def _repair_item_shapes(data: dict, chunk: str | None) -> dict:
    """Normalize common LLM shape deviations before strict validation.

    Local models frequently return "content" instead of the contract's
    "title" + "description", and omit "source_span.quote" while still
    giving start/end. Repair both: split content into a short title and a
    description, and recover the verbatim quote from the chunk text.
    """
    for item in data.get("items", []):
        if not isinstance(item, dict):
            continue
        if "title" not in item and item.get("content"):
            content = str(item.pop("content")).strip()
            head, _, tail = content.partition(". ")
            item["title"] = head.strip()[:60]
            if tail.strip():
                item["description"] = f"{head.strip()}. {tail.strip()}"
            else:
                item["description"] = head.strip()
        span = item.get("source_span")
        if isinstance(span, dict) and not span.get("quote") and chunk is not None:
            start, end = span.get("start"), span.get("end")
            if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(chunk):
                span["quote"] = chunk[start:end].strip()
    return data


def parse_extraction_text(text: str, chunk: str | None = None) -> ExtractionOutput | None:
    """Parse raw LLM text into ExtractionOutput with repair retries.

    Degradation ladder (6.4):
      - try strict JSON parse (L1/L2 output);
      - strip code fences and retry (L3, up to 2 repair attempts);
      - return None on final failure -> caller marks extraction as failed and
        routes to manual entry (L4).

    Args:
        text: Raw LLM reply.
        chunk: The transcript chunk the extraction ran on; used to recover
            missing ``source_span.quote`` values from start/end positions.

    Returns:
        Parsed output, or None when unrepairable.
    """
    candidates = [text.strip()]
    stripped = _strip_code_fences(text)
    if stripped != text.strip():
        candidates.append(stripped)

    for attempt, raw in enumerate(candidates):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = _repair_item_shapes(data, chunk)
            return ExtractionOutput.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("Extraction JSON parse failed (attempt %d): %s", attempt + 1, exc)

    logger.error("Extraction output unrepairable after retries (L4: manual entry)")
    return None


def _strip_code_fences(text: str) -> str:
    """Remove Markdown code fences some local models wrap JSON in."""
    t = text.strip()
    if t.startswith("```"):
        first_newline = t.find("\n")
        if first_newline != -1:
            t = t[first_newline + 1 :]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()
