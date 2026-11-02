"""Provider semaphore tests: per-provider concurrency convergence for Send fan-out.

Author: Wang, Bing <colin2wang@gmail.com>
"""

import asyncio
from types import SimpleNamespace

import pytest

from eep.ai_providers.semaphores import ProviderSemaphores
from eep.config import Provider


def _cfg_with_concurrency(name: str, n: int) -> SimpleNamespace:
    """Minimal stand-in exposing the ``providers`` list ProviderSemaphores reads."""
    provider = Provider(
        name=name,
        type="lmstudio",
        base_url="http://localhost:1234",
        api_key="k",
        max_concurrency=n,
    )
    return SimpleNamespace(providers=[provider])


async def test_semaphore_limits_concurrency() -> None:
    sems = ProviderSemaphores(_cfg_with_concurrency("p", 2))
    active = 0
    peak = 0

    async def _work() -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1

    await asyncio.gather(*[sems.run("p", _work) for _ in range(10)])
    assert peak == 2  # never more than max_concurrency in flight


async def test_semaphore_unknown_provider_runs_unbounded() -> None:
    sems = ProviderSemaphores(_cfg_with_concurrency("p", 1))

    async def _work() -> str:
        return "ok"

    assert await sems.run("unknown", _work) == "ok"


async def test_semaphore_propagates_result_and_exception() -> None:
    sems = ProviderSemaphores(_cfg_with_concurrency("p", 1))

    async def _value() -> int:
        return 42

    async def _boom() -> None:
        raise ValueError("x")

    assert await sems.run("p", _value) == 42
    with pytest.raises(ValueError):
        await sems.run("p", _boom)
