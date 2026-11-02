"""Standardized logging + streaming invocation for LLM calls.

All LLM invocations go through :func:`invoke_llm`, which streams via the
chat model's underlying OpenAI-compatible client and emits standardized
entries on the ``eep.llm`` logger (INFO level, stdout):

- ``LLM CALL``   right before the request: call-site, routing role,
  provider base URL, configured model, prompt size and the full prompt;
- ``LLM REASONING`` while the model streams its thinking (streamed at
  DEBUG per chunk, summarized at INFO in the result entry);
- ``LLM RESULT`` when the reply completes: wall-clock duration, actual
  serving model, token usage (input/output/total), finish reason, the
  full reasoning traces and the final content.

Why streaming via ``llm.async_client`` instead of ``llm.ainvoke``:
langchain-openai's own ``stream()``/``ainvoke`` drops the
``reasoning_content`` field that LM Studio returns for thinking models
(e.g. Qwen3). Talking to the OpenAI-compatible endpoint directly lets us
capture ``delta.reasoning_content`` separately from ``delta.content``.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("eep.llm")

# Log to stdout: the default StreamHandler writes to stderr, which JetBrains
# consoles render entirely in red (multi-line messages do not match their
# log-line pattern). A stdout handler keeps the IDE coloring neutral.
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(levelname)s:eep.llm:%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # avoid a duplicate line via the root/stderr handler

_THINK_RE = re.compile(r" +(.*?)</think>", re.DOTALL)

_ROLE_MAP = {"system": "system", "human": "user", "ai": "assistant", "tool": "tool"}


# --------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------- #
def _message_to_dict(m: Any) -> Any:
    """Normalize one message (BaseMessage / role-tuple / plain text)."""
    if hasattr(m, "content"):  # langchain BaseMessage
        return {"role": getattr(m, "type", "message"), "content": m.content}
    if isinstance(m, (tuple, list)) and len(m) == 2:
        return {"role": m[0], "content": m[1]}
    return m


def _render_input(messages: Any) -> str:
    """Render the full prompt sent to the model."""
    if isinstance(messages, str):
        return messages
    if isinstance(messages, (list, tuple)):
        return json.dumps(
            [_message_to_dict(m) for m in messages], ensure_ascii=False, default=str, indent=2
        )
    return str(messages)


def _prompt_chars(messages: Any) -> int:
    """Total character count of the prompt (across all messages)."""
    if isinstance(messages, str):
        return len(messages)
    if isinstance(messages, (list, tuple)):
        total = 0
        for m in messages:
            content = m[1] if isinstance(m, (tuple, list)) and len(m) == 2 else getattr(m, "content", m)
            total += len(str(content))
        return total
    return len(str(messages))


def _model_of(llm: Any) -> str:
    """The configured model name on the chat model instance."""
    return str(getattr(llm, "model_name", "") or getattr(llm, "model", "") or "unknown")


def _base_url_of(llm: Any) -> str:
    """The OpenAI-compatible base URL the model is bound to."""
    return str(getattr(llm, "openai_api_base", "") or "unknown")


def _usage_of(response: Any) -> dict[str, Any]:
    """Token usage from a response / streamed result."""
    usage: dict[str, Any] = {}
    meta = getattr(response, "usage_metadata", None)
    if isinstance(meta, dict):
        usage["input_tokens"] = meta.get("input_tokens")
        usage["output_tokens"] = meta.get("output_tokens")
        usage["total_tokens"] = meta.get("total_tokens")
    else:  # raw OpenAI-style token_usage in response_metadata
        tu = (getattr(response, "response_metadata", None) or {}).get("token_usage") or {}
        usage["input_tokens"] = tu.get("prompt_tokens")
        usage["output_tokens"] = tu.get("completion_tokens")
        usage["total_tokens"] = tu.get("total_tokens")
    return {k: v for k, v in usage.items() if v is not None}


def _finish_reason_of(response: Any) -> str:
    meta = getattr(response, "response_metadata", None) or {}
    return str(meta.get("finish_reason") or "unknown")


def _render_output(response: Any) -> str:
    """Render the full reply: reasoning traces first, then the final content."""
    parts: list[str] = []
    kwargs = getattr(response, "additional_kwargs", {}) or {}
    for key in ("reasoning_content", "reasoning"):
        if kwargs.get(key):
            parts.append(f"[reasoning/{key}]\n{kwargs[key]}")
    content = getattr(response, "content", response)
    if isinstance(content, str):  # Qwen3-style inline reasoning when the server does not split it out
        think = [m.group(1).strip() for m in _THINK_RE.finditer(content)]
        if think:
            parts.append("[reasoning/think]\n" + "\n\n".join(think))
            content = _THINK_RE.sub("", content).strip()
    if kwargs:
        try:
            parts.append(
                "[additional_kwargs]\n"
                + json.dumps(kwargs, ensure_ascii=False, default=str, indent=2)
            )
        except Exception:  # noqa: BLE001 - logging must never raise
            parts.append(f"[additional_kwargs]\n{kwargs!r}")
    parts.append(f"[content]\n{content}")
    return "\n\n".join(parts)


# --------------------------------------------------------------------- #
# Streaming invocation wrapper
# --------------------------------------------------------------------- #
@dataclass
class StreamedResult:
    """Uniform result shape produced by :func:`invoke_llm`.

    Exposes the same attributes downstream code reads from an AIMessage
    (``content``) plus the reasoning captured from the stream.
    """

    content: str
    reasoning: str
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = "unknown"
    model_name: str = ""

    @property
    def additional_kwargs(self) -> dict[str, Any]:
        """Reasoning exposed the way AIMessage surfaces it (for the renderer)."""
        return {"reasoning_content": self.reasoning} if self.reasoning else {}

    @property
    def response_metadata(self) -> dict[str, Any]:
        return {"model_name": self.model_name, "finish_reason": self.finish_reason}


def _build_payload(llm: Any, messages: Any) -> dict[str, Any]:
    """Build the raw OpenAI chat-completions request body."""
    if isinstance(messages, str):
        rendered = [{"role": "user", "content": messages}]
    else:
        rendered = []
        for m in messages:
            d = _message_to_dict(m)
            role = _ROLE_MAP.get(str(d.get("role")), str(d.get("role")))
            rendered.append({"role": role, "content": d.get("content")})

    payload: dict[str, Any] = {
        "model": _model_of(llm),
        "messages": rendered,
        "temperature": getattr(llm, "temperature", 0.1),
    }
    max_tokens = getattr(llm, "max_tokens", None)
    if max_tokens:
        payload["max_tokens"] = max_tokens
    reasoning_effort = getattr(llm, "reasoning_effort", None)
    if reasoning_effort:  # e.g. "none" disables Qwen3 thinking on LM Studio
        payload["reasoning_effort"] = reasoning_effort
    payload.update(getattr(llm, "extra_body", {}) or {})
    return payload


async def invoke_llm(site: str, role: str, llm: Any, messages: Any) -> StreamedResult:
    """Invoke a chat model with streaming and standardized logging.

    Streams through ``llm.async_client`` so ``delta.reasoning_content``
    (thinking traces) is captured separately from ``delta.content`` —
    langchain's own ``ainvoke``/``stream`` would drop the former. Falls back
    to a non-streaming ``llm.ainvoke`` when the streaming request fails.

    Logs ``LLM CALL`` (prompt) before the request and ``LLM RESULT``
    (duration, serving model, token usage, finish reason, reasoning,
    content) afterwards. Errors are logged as ``LLM ERROR`` and re-raised
    only when the non-streaming fallback also fails.

    Returns:
        A :class:`StreamedResult` with ``content`` (final answer text).
    """
    payload = _build_payload(llm, messages)
    logger.info(
        "=== LLM CALL [site=%s role=%s provider_base=%s model=%s prompt_chars=%d] ===\n%s",
        site,
        role,
        _base_url_of(llm),
        payload["model"],
        _prompt_chars(messages),
        _render_input(messages),
    )

    start = time.perf_counter()
    reasoning_parts: list[str] = []
    content_parts: list[str] = []
    usage: dict[str, Any] = {}
    finish = "unknown"
    streamed = False
    try:
        # langchain-openai exposes either AsyncOpenAI (-> .chat.completions)
        # or the AsyncCompletions resource directly, depending on version.
        client = llm.async_client
        if hasattr(client, "chat"):
            client = client.chat.completions
        stream_payload = {**payload, "stream": True, "stream_options": {"include_usage": True}}
        response = await client.create(**stream_payload)
        async for chunk in response:
            if getattr(chunk, "usage", None):
                usage = {
                    "input_tokens": chunk.usage.prompt_tokens,
                    "output_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue
            delta = choice.delta
            rc = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
            piece = getattr(delta, "content", None)
            if rc:
                if not reasoning_parts:
                    logger.info("=== LLM REASONING [site=%s role=%s] (streaming, DEBUG per chunk) ===", site, role)
                reasoning_parts.append(rc)
                logger.debug("%s", rc)
            if piece:
                content_parts.append(piece)
            if choice.finish_reason:
                finish = choice.finish_reason
        streamed = True
    except Exception as stream_exc:  # noqa: BLE001 - fall back to non-streaming
        logger.info(
            "=== LLM ERROR [site=%s role=%s model=%s duration=%.3fs falling back to non-streaming] ===\n%s",
            site,
            role,
            payload["model"],
            time.perf_counter() - start,
            stream_exc,
        )
        fallback = await llm.ainvoke(messages)
        usage = _usage_of(fallback)
        finish = _finish_reason_of(fallback)
        kwargs = getattr(fallback, "additional_kwargs", {}) or {}
        reasoning = str(kwargs.get("reasoning_content") or "")
        result = StreamedResult(
            content=str(fallback.content),
            reasoning=reasoning,
            usage=usage,
            finish_reason=finish,
            model_name=str((getattr(fallback, "response_metadata", None) or {}).get("model_name") or payload["model"]),
        )
        logger.info(
            "=== LLM RESULT [site=%s role=%s model=%s serving_model=%s duration=%.3fs stream=false "
            "tokens(in/out/total)=%s finish=%s] ===\n%s",
            site,
            role,
            payload["model"],
            result.model_name,
            time.perf_counter() - start,
            "/".join(str(usage.get(k, "-")) for k in ("input_tokens", "output_tokens", "total_tokens")),
            finish,
            _render_output(result),
        )
        return result

    elapsed = time.perf_counter() - start
    result = StreamedResult(
        content="".join(content_parts).strip(),
        reasoning="".join(reasoning_parts).strip(),
        usage=usage,
        finish_reason=finish,
        model_name=str(payload["model"]),
    )
    if not streamed:  # pragma: no cover - defensive, stream always sets it
        result.content = result.content or ""
    logger.info(
        "=== LLM RESULT [site=%s role=%s model=%s serving_model=%s duration=%.3fs stream=true "
        "tokens(in/out/total)=%s finish=%s] ===\n%s",
        site,
        role,
        payload["model"],
        result.model_name,
        elapsed,
        "/".join(str(usage.get(k, "-")) for k in ("input_tokens", "output_tokens", "total_tokens")),
        finish,
        _render_output(result),
    )
    return result
