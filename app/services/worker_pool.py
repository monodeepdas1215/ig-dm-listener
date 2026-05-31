import asyncio
import logging
from typing import Callable, Coroutine, Any, Awaitable, TypeVar
from dataclasses import dataclass, field
from app.services.resilient_caller import ResilientCaller, RetryConfig

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class ThrottleConfig:
    max_concurrent: int = 2
    inter_call_delay_max: float = 0.0
    retry_config: RetryConfig = field(default_factory=RetryConfig)


class ThrottledPool:
    """Rate-limit-aware worker pool with per-task retry."""
    
    def __init__(self, config: ThrottleConfig):
        self.config = config
        self.caller = ResilientCaller(config.retry_config)
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        self._dispatch_lock = asyncio.Lock()  # Serializes dispatch timing
    
    async def run(self, tasks: list[Callable[[], Awaitable[T]]]) -> list[T | Exception]:
        """Execute task callables with throttling and retry."""
        import random
        
        async def _bounded_task(task_fn: Callable[[], Awaitable[T]]) -> T | Exception:
            async with self._semaphore:
                # Dispatch lock ensures delays are serialized even with multiple semaphore slots
                if self.config.inter_call_delay_max > 0:
                    async with self._dispatch_lock:
                        delay = random.uniform(0, self.config.inter_call_delay_max)
                        if delay > 0:
                            logger.debug(f"Throttling: dispatch sleep for {delay:.2f}s")
                            await asyncio.sleep(delay)
                
                try:
                    # Pass the callable directly to caller.call so it can retry
                    return await self.caller.call(task_fn)
                except Exception as e:
                    logger.error(f"Task failed after all retries (if applicable): {e}")
                    return e

        logger.info(f"Starting {len(tasks)} tasks with max_concurrent={self.config.max_concurrent}")
        bounded_tasks = [_bounded_task(task_fn) for task_fn in tasks]
        results = await asyncio.gather(*bounded_tasks, return_exceptions=True)
                
        return results


class WorkerPoolService:
    @staticmethod
    async def run_concurrently(tasks: list[Coroutine[Any, Any, Any]], max_concurrent: int = 5) -> list[Any]:
        """
        [DEPRECATED] Executes a list of async tasks concurrently.
        Use ThrottledPool for new code as it supports retry and inter-call delay.
        """
        logger.warning("WorkerPoolService.run_concurrently is deprecated. Use ThrottledPool.")
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _bounded_task(task: Coroutine[Any, Any, Any]) -> Any:
            async with semaphore:
                return await task

        logger.info(f"Starting {len(tasks)} tasks with max_concurrent={max_concurrent}")
        bounded_tasks = [_bounded_task(task) for task in tasks]
        results = await asyncio.gather(*bounded_tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Task {i} failed with exception: {result}")
                
        return results
