"""Extraction prompt / JSON repair ladder tests.

Author: Wang, Bing <colin2wang@gmail.com>
"""

import json

from eep.graphs.extraction_prompt import (
    build_extract_user_prompt,
    parse_extraction_text,
)

VALID = {
    "items": [
        {
            "type": "action",
            "title": "Submit pilot materials",
            "owner_hint": "Huang Tao",
            "due_hint": None,
            "source_span": {"start": 10, "end": 40, "quote": "Huang Tao submits materials"},
            "confidence": 0.9,
        }
    ]
}


def test_parse_strict_json() -> None:
    out = parse_extraction_text(json.dumps(VALID, ensure_ascii=False))
    assert out is not None
    assert out.items[0].type == "action"


def test_parse_code_fenced() -> None:
    fenced = "```json\n" + json.dumps(VALID, ensure_ascii=False) + "\n```"
    out = parse_extraction_text(fenced)
    assert out is not None and out.items[0].title == "Submit pilot materials"


def test_parse_garbage_returns_none() -> None:
    assert parse_extraction_text("not json at all {{{") is None


def test_invalid_type_rejected() -> None:
    bad = {"items": [{"type": "joke", "title": "x",
                      "source_span": {"start": 1, "end": 2, "quote": "q"}}]}
    assert parse_extraction_text(json.dumps(bad)) is None


def test_user_prompt_contains_chunk() -> None:
    prompt = build_extract_user_prompt("transcript body", similar="- a decision")
    assert "transcript body" in prompt
    assert "a decision" in prompt
