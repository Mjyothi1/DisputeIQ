"""Loader for the single rules configuration file (reason_codes.yaml)."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

CONFIG_PATH = Path(__file__).with_name("reason_codes.yaml")


class Thresholds(BaseModel):
    auto_confidence: float = Field(ge=0, le=1)
    auto_max_amount_inr: float = Field(gt=0)
    auto_resolve_codes: list[str]
    duplicate_window_hours: int = Field(gt=0)
    amount_tolerance_pct: float = Field(ge=0)
    match_window_days: int = Field(gt=0)
    min_match_score: float = Field(ge=0, le=1)
    frequent_disputer_count: int = Field(gt=0)
    history_lookback_days: int = Field(gt=0)


class ReasonCodeSpec(BaseModel):
    code: str = ""
    description: str
    window_days: int = Field(gt=0)
    required_evidence: list[str]
    weakened_by: list[str]
    typical_evidence: list[str]


class RulesConfig(BaseModel):
    thresholds: Thresholds
    reason_codes: dict[str, ReasonCodeSpec]

    def spec(self, code: str) -> ReasonCodeSpec:
        """Return the spec for ``code``; raises KeyError for unknown codes."""
        return self.reason_codes[code]

    @property
    def codes(self) -> list[str]:
        return list(self.reason_codes)


def load_rules_config(path: Path = CONFIG_PATH) -> RulesConfig:
    """Parse and validate the YAML file; also checks the auto-resolve allow-list."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg = RulesConfig.model_validate(raw)
    for code, spec in cfg.reason_codes.items():
        spec.code = code
    unknown = set(cfg.thresholds.auto_resolve_codes) - set(cfg.reason_codes)
    if unknown:
        raise ValueError(f"auto_resolve_codes contains unknown codes: {sorted(unknown)}")
    return cfg


@lru_cache
def get_rules_config() -> RulesConfig:
    """Cached rules configuration."""
    return load_rules_config()
