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
