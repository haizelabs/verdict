import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from verdict.model import ModelSelectionPolicy
from verdict.util.ratelimit import (
    ConcurrentRateLimiter,
    RateLimitPolicy,
    TimeWindowRateLimiter,
)


# Global state
@dataclass
class Config:
    rate_limiter_disabled: bool = False


state = Config()

# Defaults
## Rate limiting
PROVIDER_RATE_LIMITER: Dict[str, RateLimitPolicy] = {
    "deepinfra": RateLimitPolicy(
        {ConcurrentRateLimiter(max_concurrent=200): "requests"}
    ),
    "together_ai": RateLimitPolicy.of(rpm=600, tpm=180_000),
    "openai": RateLimitPolicy(
        {  # tier 1 for gpt-4o-mini
            TimeWindowRateLimiter(max_value=5, window_seconds=60): "requests",
            TimeWindowRateLimiter(
                max_value=10_000, window_seconds=60 * 60 * 24
            ): "requests",
            TimeWindowRateLimiter(max_value=200_000, window_seconds=60): "tokens",
        }
    ),
    # TODO: add other providers
}

DEFAULT_RATE_LIMITER: RateLimitPolicy = PROVIDER_RATE_LIMITER["openai"]

## Connection parameters
DEFAULT_PROVIDER_TIMEOUT: int = 120
DEFAULT_PROVIDER_STREAM_TIMEOUT: int = 120

## Inference parameters
DEFAULT_MODEL_SELECTION_POLICY: ModelSelectionPolicy = ModelSelectionPolicy.from_name(
    "gpt-4o-mini", retries=3
)
DEFAULT_INFERENCE_PARAMS: dict[str, Any] = {}

## Token extraction prompt
TOKEN_EXTRACTOR_SPECIFICATION_PROMPT: str = """
{content}
--------------------------------

Do not explain your answer. {scale_prompt}
"""

# System
## Logging
DEBUG: bool = bool(os.getenv("DEBUG", False))

LIGHTWEIGHT_EXECUTOR_WORKER_COUNT: int = 32

VERDICT_LOG_DIR: Path = Path.cwd() / ".verdict"
VERDICT_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Caching / Reproducibility
CACHE_ENABLED: bool = bool(os.getenv("VERDICT_CACHE", False)) and not bool(
    os.getenv("VERDICT_NO_CACHE", False)
)
# Directory for content-addressed cache files
CACHE_DIR: Path = VERDICT_LOG_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# If set, treat cache as resume (read + write). Default semantics are identical; the
# flag exists for discoverability and future specialization.
RESUME_ON_CACHE: bool = bool(os.getenv("VERDICT_RESUME", False))

# Cost / pricing (USD per 1k tokens). These are conservative placeholders. Override
# via environment variables for accurate accounting in your environment.
DEFAULT_PRICE_IN_PER_KTOK: float = float(os.getenv("VERDICT_PRICE_IN_PER_KTOK", "0.0"))
DEFAULT_PRICE_OUT_PER_KTOK: float = float(
    os.getenv("VERDICT_PRICE_OUT_PER_KTOK", "0.0")
)

# Optional model-specific pricing. Keys are provider or fully qualified model
# names (e.g., "openai/gpt-4o-mini"). Values are dicts with "in" and "out".
PRICING: Dict[str, Dict[str, float]] = {
    # Example entries (override via env or edit for your org):
    # "openai/gpt-4o-mini": {"in": 0.15, "out": 0.6},
}

def get_pricing_for_model(model_name: str, provider: str | None = None) -> tuple[float, float]:
    key_full = model_name
    key_provider = provider or model_name.split("/")[0]
    if key_full in PRICING:
        d = PRICING[key_full]
        return d.get("in", DEFAULT_PRICE_IN_PER_KTOK), d.get("out", DEFAULT_PRICE_OUT_PER_KTOK)
    if key_provider in PRICING:
        d = PRICING[key_provider]
        return d.get("in", DEFAULT_PRICE_IN_PER_KTOK), d.get("out", DEFAULT_PRICE_OUT_PER_KTOK)
    return DEFAULT_PRICE_IN_PER_KTOK, DEFAULT_PRICE_OUT_PER_KTOK
