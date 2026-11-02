"""ModelFactory tests: role routing, breaker fallback, /v1 normalization.

Author: Wang, Bing <colin2wang@gmail.com>
"""

import pytest

from eep.ai_providers import ModelFactory, ProviderUnavailableError
from eep.ai_providers.model_factory import OPENAI_COMPAT_TYPES
from eep.config import AIConfig, BreakerConfig, FallbackPolicy, Provider, RoleConfig


def make_cfg() -> AIConfig:
    return AIConfig.model_validate(
        {
            "providers": [
                {
                    "name": "a",
                    "type": "lmstudio",
                    "base-url": "http://localhost:1234",
                    "models": {"chat": "m-a"},
                },
                {
                    "name": "b",
                    "type": "ollama",
                    "base-url": "http://localhost:11434/",
                    "models": {"chat": "m-b"},
                },
            ],
            "roles": {
                "extractor": {
                    "primary": "a/m-a",
                    "fallback": ["b/m-b"],
                    "temperature": 0.1,
                }
            },
        }
    )


def test_base_url_appends_v1() -> None:
    mf = ModelFactory(make_cfg())
    p = mf.providers["b"]
    assert ModelFactory._base_url(p) == "http://localhost:11434/v1"  # trailing slash stripped


def test_openai_compat_types() -> None:
    assert {"lmstudio", "ollama", "vllm"} <= OPENAI_COMPAT_TYPES


def test_unknown_role_raises_keyerror() -> None:
    mf = ModelFactory(make_cfg())
    with pytest.raises(KeyError):
        mf.get_chat_model("nonexistent")


def test_breaker_opens_after_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = make_cfg()
    cfg.fallback_policy = FallbackPolicy(breaker=BreakerConfig(failure_threshold=2, open_seconds=120))
    mf = ModelFactory(cfg)
    breaker = mf._breakers["a"]
    breaker.record_failure()
    assert not breaker.is_open
    breaker.record_failure()
    assert breaker.is_open  # threshold reached -> skip primary


def test_breaker_state_snapshot() -> None:
    mf = ModelFactory(make_cfg())
    assert mf.breaker_state() == {"a": "closed", "b": "closed"}


def test_all_providers_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = make_cfg()
    # Make both providers non-OpenAI-compatible so no candidate can build.
    for p in cfg.providers:
        p.type = "unknown-type"
    mf = ModelFactory(cfg)
    with pytest.raises(ProviderUnavailableError):
        mf.get_chat_model("extractor")
