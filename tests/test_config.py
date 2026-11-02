"""Config layer tests: ai-providers.yaml parsing and validation.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from eep.config import load_ai_config

CFG = Path(__file__).resolve().parents[1] / "ai-providers.yaml"


def test_load_real_yaml() -> None:
    cfg = load_ai_config(CFG)
    names = {p.name for p in cfg.providers}
    assert {"lmstudio-local", "ollama-local"} <= names
    assert set(cfg.roles) >= {"extractor", "summarizer", "linker", "memory-manager"}


def test_kebab_case_aliases() -> None:
    cfg = load_ai_config(CFG)
    lm = next(p for p in cfg.providers if p.name == "lmstudio-local")
    assert lm.base_url == "http://localhost:1234"  # bare, no /v1
    assert lm.max_concurrency == 2
    assert lm.timeout_seconds == 600


def test_role_primary_format() -> None:
    cfg = load_ai_config(CFG)
    extractor = cfg.roles["extractor"]
    assert "/" in extractor.primary
    assert extractor.fallback  # extractor has a fallback chain


def test_invalid_yaml_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("ai:\n  providers:\n    - name: x\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_ai_config(bad)
