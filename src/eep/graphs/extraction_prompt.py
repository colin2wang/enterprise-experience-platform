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

# Appendix B prompt skeleton, tuned for Qwen2.5, in English for consistency.
EXTRACT_SYSTEM_PROMPT = """\
You are an enterprise meeting experience extractor. Extract structured
experience items from the given meeting transcript chunk.
Rules:
1. Extract only items with clear evidence in the chunk; every item MUST include
   a source_span (character start/end positions in the chunk plus the verbatim
   quote);
2. Five types: question = open question to solve; hypothesis = claim to verify;
   experiment = planned verification activity; decision = a decision already
   made; action = a next step someone must execute;
3. For actions, always try to provide owner_hint and due_hint; if missing, set
   them to null (the UI shows "unclaimed" / "TBD");
4. When uncertain, prefer omitting the item. NEVER fabricate. confidence
   reflects your certainty;
5. Output strictly conforms to the JSON Schema.
"""

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


def build_extract_user_prompt(chunk: str, similar: str) -> str:
    """Assemble the user message: chunk + similar library context."""
    return f"[Transcript chunk]\n{chunk}\n\n[Context: similar experiences in library, avoid duplicates]\n{similar}"


def parse_extraction_text(text: str) -> ExtractionOutput | None:
    """Parse raw LLM text into ExtractionOutput with repair retries.

    Degradation ladder (6.4):
      - try strict JSON parse (L1/L2 output);
      - strip code fences and retry (L3, up to 2 repair attempts);
      - return None on final failure -> caller marks extraction as failed and
        routes to manual entry (L4).

    Returns:
        Parsed output, or None when unrepairable.
    """
    candidates = [text.strip()]
    stripped = _strip_code_fences(text)
    if stripped != text.strip():
        candidates.append(stripped)

    for attempt, raw in enumerate(candidates):
        try:
            return ExtractionOutput.model_validate(json.loads(raw))
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
