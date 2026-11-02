"""Circuit breaker and health probe tests (httpx mocked via monkeypatch).

Author: Wang, Bing <colin2wang@gmail.com>
"""

import time

import httpx
import pytest

from eep.ai_providers.health import Breaker, BreakerOpenError, probe
from eep.config import BreakerConfig, Provider


# ------------------------------------------------------------------ #
# Circuit breaker
# ------------------------------------------------------------------ #
def _breaker(threshold: int = 3, open_seconds: float = 0.05) -> Breaker:
    return Breaker(
        name="test",
        config=BreakerConfig(failure_threshold=threshold, open_seconds=open_seconds),
    )


def test_breaker_opens_after_consecutive_failures() -> None:
    b = _breaker(threshold=3)
    b.record_failure()
    b.record_failure()
    assert not b.is_open
    b.record_failure()
    assert b.is_open


def test_breaker_success_resets_failure_streak() -> None:
    b = _breaker(threshold=3)
    b.record_failure()
    b.record_failure()
    b.record_success()
    b.record_failure()
    b.record_failure()
    assert not b.is_open  # never reached 3 consecutive


def test_breaker_half_open_after_open_seconds() -> None:
    b = _breaker(threshold=1, open_seconds=0.01)
    b.record_failure()
    assert b.is_open
    time.sleep(0.02)
    assert not b.is_open  # half-open: one attempt allowed through again


def test_breaker_open_error_is_runtime_error() -> None:
    assert issubclass(BreakerOpenError, RuntimeError)


# ------------------------------------------------------------------ #
# Health probe (httpx mocked)
# ------------------------------------------------------------------ #
def _provider(name: str = "lmstudio-local", chat: str = "qwen2.5-32b-instruct") -> Provider:
    return Provider(
        name=name,
        type="lmstudio",
        base_url="http://localhost:1234",
        api_key="k",
        models={"chat": chat},
    )


async def test_probe_connected_reports_models(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self, url, **kwargs):
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            request=request,
            json={"data": [{"id": "qwen2.5-32b-instruct"}, {"id": "bge-m3"}]},
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    report = await probe(_provider())
    assert report.status == "connected"
    assert report.models == ["qwen2.5-32b-instruct", "bge-m3"]
    assert report.chat_model_ready is True


async def test_probe_chat_model_not_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self, url, **kwargs):
        request = httpx.Request("GET", url)
        return httpx.Response(200, request=request, json={"data": [{"id": "other-model"}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    report = await probe(_provider())
    assert report.status == "connected"
    assert report.chat_model_ready is False


async def test_probe_unreachable_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get(self, url, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    report = await probe(_provider())
    assert report.status == "unreachable"
    assert "connection refused" in report.detail
