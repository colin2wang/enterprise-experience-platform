"""Model factory: role-based routing, circuit breaking, /v1 normalization.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from eep.ai_providers.health import Breaker, BreakerConfig, BreakerOpenError
from eep.config import AIConfig, Provider

# Provider types that expose an OpenAI-compatible HTTP API.
OPENAI_COMPAT_TYPES = {"lmstudio", "ollama", "openai", "vllm", "xinference"}


class ProviderUnavailableError(RuntimeError):
    """Raised when neither the primary nor any fallback model is available."""


class ModelFactory:
    """Builds chat models by *role*, never by direct provider binding.

    Contract notes:
    - ``base_url`` in the YAML stays bare; this factory appends ``/v1``
      (the Spring side appends it automatically).
    - ``max_retries=0``: retries belong to graph nodes, not the SDK, to avoid
      double-layered retry loops.
    """

    def __init__(self, cfg: AIConfig) -> None:
        self.cfg = cfg
        self.providers = cfg.provider_map()
        breaker_cfg: BreakerConfig = cfg.fallback_policy.breaker
        self._breakers: dict[str, Breaker] = {
            name: Breaker(name=name, config=breaker_cfg) for name in self.providers
        }

    # ------------------------------------------------------------------ #
    # URL handling
    # ------------------------------------------------------------------ #
    @staticmethod
    def _base_url(p: Provider) -> str:
        """Normalize a bare base-url to include the ``/v1`` prefix."""
        base = p.base_url.rstrip("/")
        return base if base.endswith("/v1") else f"{base}/v1"

    # ------------------------------------------------------------------ #
    # Model construction
    # ------------------------------------------------------------------ #
    def get_chat_model(self, role: str) -> ChatOpenAI:
        """Return a chat model for the given role, honoring fallback order.

        Iterates over primary then fallback candidates. Providers with an
        open breaker are skipped; construction failures trip the breaker.

        Raises:
            ProviderUnavailableError: If no candidate can be constructed.
            KeyError: If the role is unknown.
        """
        try:
            rc = self.cfg.roles[role]
        except KeyError as exc:
            raise KeyError(f"Unknown role '{role}' in ai-providers.yaml") from exc

        last_error: Exception | None = None
        for candidate in [rc.primary, *rc.fallback]:
            provider_name, model = candidate.split("/", 1)
            p = self.providers.get(provider_name)
            if p is None or p.type not in OPENAI_COMPAT_TYPES:
                continue
            if self._breakers[provider_name].is_open:
                continue  # breaker open -> fall through to fallback
            try:
                llm = ChatOpenAI(
                    model=model,
                    base_url=self._base_url(p),
                    api_key=p.api_key,
                    temperature=rc.temperature,
                    max_tokens=p.max_tokens,
                    timeout=p.timeout_seconds,
                    max_retries=0,
                )
                self._breakers[provider_name].record_success()
                return llm
            except Exception as exc:  # noqa: BLE001 - try next fallback
                last_error = exc
                self._breakers[provider_name].record_failure()

        raise ProviderUnavailableError(
            f"No available provider for role '{role}'"
            + (f"; last error: {last_error}" if last_error else "")
        )

    def structured_output_mode(self, role: str) -> str | None:
        """Return the structured-output mode configured for the role."""
        return self.cfg.roles[role].structured_output if role in self.cfg.roles else None

    def breaker_state(self) -> dict[str, str]:
        """Snapshot of breaker states, for the health aggregation endpoint."""
        return {name: ("open" if b.is_open else "closed") for name, b in self._breakers.items()}


__all__ = [
    "OPENAI_COMPAT_TYPES",
    "BreakerOpenError",
    "ModelFactory",
    "ProviderUnavailableError",
]
