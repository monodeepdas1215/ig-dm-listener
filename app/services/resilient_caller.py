import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Callable, Any, Awaitable

logger = logging.getLogger(__name__)


# ── Error Classifiers ────────────────────────────────
# Each classifier is a function (Exception) -> bool that returns True
# if the error is retryable for the given category.

def is_rate_limit_error(exc: Exception) -> bool:
    """429 rate limit errors — handled by SDK-level retries, not retryable here.

    SDKs (ZAI, OpenAI) already retry 429s internally. Treating them as retryable
    here causes double-retry: SDK retries N times, then ResilientCaller retries
    M more times on top, wasting time on permanent quota exhaustion (e.g. ZAI
    error code 1113 "Insufficient balance").
    """
    return False


def is_connection_error(exc: Exception) -> bool:
    """Check if the exception is a transient connection/network error."""
    exc_type = type(exc).__name__
    
    # Known connection error types across providers
    if exc_type in (
        "APIConnectionError",   # openai/zhipuai
        "ConnectError",         # httpx
        "ReadError",            # httpx/httpcore
        "WriteError",           # httpx/httpcore
        "PoolTimeout",          # httpx
        "ConnectTimeout",       # httpx
        "RemoteProtocolError",  # httpcore
        "BrokenResourceError",  # anyio (underlying cause in our logs)
    ):
        return True
    
    exc_str = str(exc).lower()
    connection_phrases = (
        "connection error",
        "broken pipe",
        "connection reset",
        "timed out",
        "connection refused",
        "broken resource",
        "network is unreachable",
        "name or service not known",
        "temporary failure in name resolution",
    )
    return any(phrase in exc_str for phrase in connection_phrases)


def is_server_error(exc: Exception) -> bool:
    """Check if the exception is a 5xx server error (transient)."""
    exc_type = type(exc).__name__
    
    if exc_type in ("InternalServerError", "APIInternalError"):
        return True
    
    if hasattr(exc, "response") and exc.response is not None:
        status = getattr(exc.response, "status_code", None) or \
                 getattr(exc.response, "status", None)
        if status and 500 <= status < 600:
            return True
    
    exc_str = str(exc).lower()
    return any(code in exc_str for code in ("500", "502", "503", "504", "internal server error"))


# ── Pre-built classifier sets ────────────────────────

DEFAULT_RETRYABLE_CLASSIFIERS: list[Callable[[Exception], bool]] = [
    is_rate_limit_error,
]
"""Default: only retry 429 rate limit errors. Backward-compatible with existing behavior."""

RESILIENT_CLASSIFIERS: list[Callable[[Exception], bool]] = [
    is_rate_limit_error,
    is_connection_error,
    is_server_error,
]
"""Resilient: retry rate limits, connection errors, AND server errors.
Use this for network-sensitive operations like large payload uploads."""


@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 5.0
    max_delay: float = 120.0
    jitter: bool = True
    retryable_classifiers: list[Callable[[Exception], bool]] = field(
        default_factory=lambda: list(DEFAULT_RETRYABLE_CLASSIFIERS)
    )


class ResilientCaller:
    """Wraps an async callable with retry + exponential backoff + jitter.
    
    Retry behavior is controlled by the `retryable_classifiers` list in
    RetryConfig. Each classifier is called in order — if ANY returns True,
    the error is considered retryable.
    
    Default behavior (backward-compatible): only retries 429s.
    Pass RESILIENT_CLASSIFIERS to also retry connection/server errors.
    """
    
    def __init__(self, config: RetryConfig = RetryConfig()):
        self.config = config
    
    def _is_retryable(self, exc: Exception) -> bool:
        """Check if any classifier considers this error retryable."""
        return any(clf(exc) for clf in self.config.retryable_classifiers)
    
    def _classify_error(self, exc: Exception) -> str:
        """Return a human-readable classification of the error for logging."""
        if is_rate_limit_error(exc):
            return "RATE_LIMIT"
        if is_connection_error(exc):
            return "CONNECTION"
        if is_server_error(exc):
            return "SERVER_5XX"
        return "UNKNOWN"
    
    async def call(self, fn: Callable[[], Awaitable[Any]]) -> Any:
        attempts = 0
        last_exception = None
        
        while attempts <= self.config.max_retries:
            try:
                return await fn()
            except Exception as e:
                attempts += 1
                last_exception = e
                
                if not self._is_retryable(e):
                    logger.debug(
                        f"Non-retryable error ({self._classify_error(e)}): "
                        f"{type(e).__name__} - {e}"
                    )
                    raise e
                    
                if attempts > self.config.max_retries:
                    break
                    
                # Calculate backoff with exponential increase
                delay = min(
                    self.config.base_delay * (2 ** (attempts - 1)),
                    self.config.max_delay
                )
                
                if self.config.jitter:
                    delay = random.uniform(0, delay)
                    
                # Check if there is a Retry-After header we should respect
                if hasattr(e, "response") and e.response is not None:
                    headers = getattr(e.response, "headers", {})
                    retry_after = headers.get("retry-after") or headers.get("Retry-After")
                    if retry_after:
                        try:
                            header_delay = float(retry_after)
                            delay = max(delay, header_delay)
                        except ValueError:
                            pass
                            
                error_class = self._classify_error(e)
                logger.warning(
                    f"Attempt {attempts}/{self.config.max_retries} failed "
                    f"({error_class}: {type(e).__name__}). "
                    f"Retrying in {delay:.2f}s. Error: {e}"
                )
                await asyncio.sleep(delay)
                
        # If we exhausted retries
        from agent_framework.exceptions import RetryExhaustedError
        raise RetryExhaustedError(
            f"Failed after {attempts} attempts. Last error: {last_exception}", 
            last_exception=last_exception, 
            attempts=attempts
        )
