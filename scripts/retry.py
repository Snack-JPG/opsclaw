"""Retry helpers with exponential backoff and jitter."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import ParamSpec, TypeVar

from .logger import get_logger


P = ParamSpec("P")
T = TypeVar("T")


@dataclass(frozen=True)
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: float = 0.5
    retry_on: tuple[type[BaseException], ...] = (
        ConnectionError,
        TimeoutError,
    )


def retry_call(
    fn: Callable[P, T],
    *args: P.args,
    config: RetryConfig | None = None,
    logger_name: str = "opsclaw.retry",
    **kwargs: P.kwargs,
) -> T:
    """Execute ``fn`` with bounded exponential backoff."""
    cfg = config or RetryConfig()
    log = get_logger(logger_name)

    for attempt in range(cfg.max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except cfg.retry_on as exc:
            if attempt >= cfg.max_retries:
                log.error(
                    "retry budget exhausted",
                    extra={
                        "event": {
                            "attempt": attempt + 1,
                            "maxRetries": cfg.max_retries,
                            "error": str(exc),
                        }
                    },
                )
                raise

            raw_delay = min(cfg.base_delay * (2**attempt), cfg.max_delay)
            delay = raw_delay + random.uniform(0, cfg.jitter)
            log.warning(
                "transient failure, retrying",
                extra={
                    "event": {
                        "attempt": attempt + 1,
                        "delaySeconds": round(delay, 2),
                        "error": str(exc),
                    }
                },
            )
            time.sleep(delay)
