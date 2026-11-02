"""Circuit breaker and health probe for AI providers.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

from eep.config import BreakerConfig, Provider


class BreakerOpenError(RuntimeError):
    """Raised when a provider's breaker is open and calls must fall back."""


@dataclass
class Breaker:
    """Per-provider circuit breaker.

    After ``failure_threshold`` consecutive failures the breaker opens for
    ``open_seconds``; while open, the model factory skips to the fallback
    candidate instead of hitting a dead endpoint.
    """

    name: str
    config: BreakerConfig
    _consecutive_failures: int = field(default=0, repr=False)
    _opened_at: float | None = field(default=None, repr=False)

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.config.open_seconds:
            # Half-open: allow one attempt through again.
            self._opened_at = None
            self._consecutive_failures = 0
            return False
        return True

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.config.failure_threshold:
            self._opened_at = time.monotonic()

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None


@dataclass
class HealthReport:
    """Result of probing one provider, for the /admin/ai-providers/health API."""

    provider: str
    status: str  # "connected" | "unreachable"
    models: list[str] = field(default_factory=list)
    chat_model_ready: bool = False
    detail: str = ""


async def probe(provider: Provider, chat_models: set[str] | None = None) -> HealthReport:
    """Probe an OpenAI-compatible provider via ``GET {base}/v1/models``.

    Args:
        provider: The provider entry to probe.
        chat_models: Model names the catalog assigns to this provider
            (from ``model-info.yml``); when given, ``chat_model_ready``
            reports whether the server serves at least one of them.

    Returns:
        A :class:`HealthReport` describing reachability and model readiness.
    """
    url = f"{provider.base_url.rstrip('/')}/v1/models"
    headers = {"Authorization": f"Bearer {provider.api_key}"}
    try:
        async with httpx.AsyncClient(timeout=provider.connect_timeout_seconds) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            models = [m.get("id", "") for m in data if isinstance(m, dict)]
            ready = bool(chat_models & set(models)) if chat_models is not None else False
            return HealthReport(
                provider=provider.name,
                status="connected",
                models=models,
                chat_model_ready=ready,
            )
    except Exception as exc:  # noqa: BLE001 - probe must never raise
        return HealthReport(
            provider=provider.name,
            status="unreachable",
            detail=str(exc),
        )
