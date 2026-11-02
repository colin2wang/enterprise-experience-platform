"""Provider-level semaphores to converge LangGraph `Send` parallelism.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from eep.config import AIConfig


class ProviderSemaphores:
    """Limit concurrent calls per provider (local single-GPU throttling).

    LangGraph ``Send`` fans out chunks in parallel; each provider's
    ``max-concurrency`` keeps the fan-out from overwhelming the runtime.
    """

    def __init__(self, cfg: AIConfig) -> None:
        self._semaphores: dict[str, asyncio.Semaphore] = {
            p.name: asyncio.Semaphore(p.max_concurrency) for p in cfg.providers
        }

    def run(self, provider_name: str, coro_factory: Callable[[], Awaitable[Any]]) -> Awaitable[Any]:
        """Run ``coro_factory()`` bounded by the provider's semaphore.

        Args:
            provider_name: Provider to throttle (unknown names run unbounded).
            coro_factory: Zero-arg callable producing the coroutine, so the
                coroutine is created only once the slot is acquired.

        Returns:
            An awaitable resolving to the coroutine's result.
        """
        sem = self._semaphores.get(provider_name)

        async def _bounded() -> Any:
            if sem is None:
                return await coro_factory()
            async with sem:
                return await coro_factory()

        return _bounded()


__all__ = ["ProviderSemaphores"]
