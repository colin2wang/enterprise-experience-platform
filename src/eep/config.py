"""Configuration layer.

Parses ``ai-providers.yaml`` (the single source of truth shared with the Spring
Boot backend) via pydantic models, plus service-level settings from environment
variables.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Capabilities(BaseModel):
    """Provider capability flags (mirrors the YAML ``capabilities`` block)."""

    chat: bool = True
    tool_calls: str = "partial"
    json_schema: bool = False
    embeddings: bool = False


class Provider(BaseModel):
    """One AI provider entry from ``ai-providers.yaml``."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    type: str
    base_url: str = Field(alias="base-url")  # bare address, no /v1 suffix
    api_key: str = Field(alias="api-key", default="EMPTY")
    timeout_seconds: int = Field(alias="timeout-seconds", default=600)
    connect_timeout_seconds: int = Field(alias="connect-timeout-seconds", default=10)
    max_tokens: int = Field(alias="max-tokens", default=4096)
    max_concurrency: int = Field(alias="max-concurrency", default=4)
    capabilities: Capabilities = Field(default_factory=Capabilities)
    models: dict[str, str] = Field(default_factory=dict)


class RoleConfig(BaseModel):
    """Role-based routing entry (extractor / summarizer / linker / memory-manager)."""

    model_config = ConfigDict(populate_by_name=True)

    primary: str  # "provider/model"
    fallback: list[str] = Field(default_factory=list)
    temperature: float = 0.1
    structured_output: str | None = Field(
        alias="structured-output", default=None
    )  # json_schema | json_mode | None

    @field_validator("fallback", mode="before")
    @classmethod
    def _none_to_list(cls, v: object) -> object:
        return [] if v is None else v


class EmbeddingsConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: str
    model: str
    dims: int = 1024
    batch_size: int = Field(alias="batch-size", default=32)


class RerankConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: str
    base_url: str = Field(alias="base-url")
    model: str


class BreakerConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    failure_threshold: int = Field(alias="failure-threshold", default=3)
    open_seconds: float = Field(alias="open-seconds", default=120)


class FallbackPolicy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    health_probe_seconds: int = Field(alias="health-probe-seconds", default=30)
    breaker: BreakerConfig = Field(default_factory=BreakerConfig)


class AIConfig(BaseModel):
    """Root of the ``ai:`` block in ``ai-providers.yaml``."""

    providers: list[Provider] = Field(default_factory=list)
    roles: dict[str, RoleConfig] = Field(default_factory=dict)
    embeddings: EmbeddingsConfig | None = None
    rerank: RerankConfig | None = None
    fallback_policy: FallbackPolicy = Field(
        alias="fallback-policy", default_factory=FallbackPolicy
    )

    def provider_map(self) -> dict[str, Provider]:
        """Providers indexed by name, for O(1) lookup in the model factory."""
        return {p.name: p for p in self.providers}


class Settings(BaseSettings):
    """Service-level settings (env ``EEP_*`` > eep.yml > defaults)."""

    model_config = SettingsConfigDict(env_prefix="EEP_", env_file=".env", extra="ignore")

    app_name: str = "EEP AI Pipeline Service"
    # Bind to loopback only: the web UI and API are local-dev surfaces.
    host: str = "127.0.0.1"
    port: int = 8100

    # SQLite by default: zero-setup, auto-initialized on startup.
    # Switch to PostgreSQL via eep.yml or EEP_DATABASE_URL (see eep.yml).
    database_url: str = "sqlite+aiosqlite:///./eep.db"
    redis_url: str = "redis://localhost:6379/0"

    # Path to the shared provider configuration file.
    ai_providers_path: Path = Path("ai-providers.yaml")

    # Object storage (MinIO/S3) endpoint for transcripts.
    storage_endpoint: str = "http://localhost:9000"
    storage_bucket: str = "eep"

    # Default retrieval knobs.
    vector_top_k: int = 50
    rerank_top_k: int = 8
    duplicate_similarity_threshold: float = 0.92


# eep.yml keys -> Settings fields (flat, kebab-case in YAML).
_YML_KEYS = {
    "database-url": "database_url",
    "redis-url": "redis_url",
    "ai-providers-path": "ai_providers_path",
    "storage-endpoint": "storage_endpoint",
    "storage-bucket": "storage_bucket",
    "host": "host",
    "port": "port",
    "vector-top-k": "vector_top_k",
    "rerank-top-k": "rerank_top_k",
}

_DEFAULT_SETTINGS = Settings()


def load_app_config(path: Path | str | None = None) -> Settings:
    """Build service settings with precedence: env vars > eep.yml > defaults.

    Args:
        path: Config file path; defaults to ``./eep.yml`` (optional file).

    Returns:
        A :class:`Settings` where every value is resolved in that order.
    """
    import os

    p = Path(path) if path else Path("eep.yml")
    yml: dict[str, object] = {}
    if p.exists():
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        yml = {k: v for k, v in raw.items() if k in _YML_KEYS}

    values: dict[str, object] = {}
    for yml_key, field in _YML_KEYS.items():
        # 1) environment variable always wins
        env_val = os.environ.get(f"EEP_{field.upper()}")
        if env_val is not None:
            values[field] = env_val
            continue
        # 2) eep.yml value
        if yml_key in yml:
            values[field] = yml[yml_key]
        # 3) otherwise the dataclass default from Settings applies
    return Settings(**values)


def load_ai_config(path: Path | str | None = None) -> AIConfig:
    """Load and validate ``ai-providers.yaml``.

    Args:
        path: Override path; defaults to ``Settings.ai_providers_path``.

    Returns:
        A validated :class:`AIConfig`.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        pydantic.ValidationError: If the YAML does not match the contract.
    """
    p = Path(path) if path else Settings().ai_providers_path
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    ai_block = raw.get("ai") or {}
    return AIConfig.model_validate(ai_block)
