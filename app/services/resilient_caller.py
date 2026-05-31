import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Callable, Any, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 5.0
    max_delay: float = 120.0
    jitter: bool = True
    retryable_status_codes: set[int] = field(default_factory=lambda: {429})


def is_429_error(exc: Exception) -> bool:
    """Check if the exception is a 429 rate limit error."""
    exc_type = type(exc).__name__
    
    # Langchain/Provider specific rate limit errors
    if exc_type in ("RateLimitError", "ResourceExhausted", "ResourceExhaustedError"):
        return True
        
    # httpx/requests/aiohttp status errors
    if hasattr(exc, "response") and exc.response is not None:
        if hasattr(exc.response, "status_code"):
            if exc.response.status_code == 429:
                return True
        if hasattr(exc.response, "status"):
            if exc.response.status == 429:
                return True
                
    # fallback to string matching
    exc_str = str(exc).lower()
    if "429" in exc_str or "too many requests" in exc_str or "rate limit" in exc_str:
        return True
        
    return False


class ResilientCaller:
    """Wraps an async callable with retry + exponential backoff + jitter, ONLY for 429s."""
    
    def __init__(self, config: RetryConfig = RetryConfig()):
        self.config = config
    
    async def call(self, fn: Callable[[], Awaitable[Any]]) -> Any:
        attempts = 0
        last_exception = None
        
        while attempts <= self.config.max_retries:
            try:
                return await fn()
            except Exception as e:
                attempts += 1
                last_exception = e
                
                # We ONLY retry on 429s
                if not is_429_error(e):
                    logger.debug(f"Non-retryable error encountered: {type(e).__name__} - {e}")
                    raise e
                    
                if attempts > self.config.max_retries:
                    break
                    
                # Calculate backoff with exponential increase
                delay = min(self.config.base_delay * (2 ** (attempts - 1)), self.config.max_delay)
                
                if self.config.jitter:
                    delay = random.uniform(0, delay)
                    
                # Check if there is a Retry-After header we should respect
                if hasattr(e, "response") and e.response is not None:
                    headers = getattr(e.response, "headers", {})
                    retry_after = headers.get("retry-after") or headers.get("Retry-After")
                    if retry_after:
                        try:
                            # Usually seconds
                            header_delay = float(retry_after)
                            delay = max(delay, header_delay)
                        except ValueError:
                            pass
                            
                logger.warning(
                    f"Attempt {attempts} failed with 429 Rate Limit. "
                    f"Retrying in {delay:.2f} seconds. Error: {e}"
                )
                await asyncio.sleep(delay)
                
        # If we exhausted retries
        from agent_framework.exceptions import RetryExhaustedError
        raise RetryExhaustedError(
            f"Failed after {attempts} attempts. Last error: {last_exception}", 
            last_exception=last_exception, 
            attempts=attempts
        )
