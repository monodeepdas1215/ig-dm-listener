import logging
from typing import Any
from zai import ZaiClient

logger = logging.getLogger(__name__)


class ZaiCaller:
    """Native ZAI SDK wrapper for GLM models.
    
    Provides an async `invoke()` method that mirrors LangChain's
    `ainvoke()` contract but uses the native zai-sdk directly.
    
    Returns raw `str` content, not a LangChain `AIMessage`.
    Accepts plain `dict` messages (OpenAI-compatible format).
    Timeout and retry are configured at the SDK level.
    """
    
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        timeout: int = 300,
        max_retries: int = 2,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        **kwargs,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        self._client = ZaiClient(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        logger.info(
            f"ZaiCaller initialized: model={model}, base_url={base_url}, "
            f"timeout={timeout}s, max_retries={max_retries}"
        )
    
    def invoke_sync(self, messages: list[dict], model_override: str | None = None) -> str:
        """Synchronous method to send messages to GLM and return text response."""
        model_to_use = model_override or self.model
        logger.debug(f"ZaiCaller.invoke_sync: model={model_to_use}, messages_count={len(messages)}")
        
        kwargs = {
            "model": model_to_use,
            "messages": messages,
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens
        
        response = self._client.chat.completions.create(**kwargs)
        
        content = response.choices[0].message.content
        
        # GLM can return content as list or string — normalize to string
        if isinstance(content, list):
            # Join text parts, ignoring non-text items
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item["text"])
            content = "\n".join(parts)
        
        logger.debug(f"ZaiCaller.invoke_sync: response length={len(content)} chars")
        return content

    async def invoke(self, messages: list[dict], model_override: str | None = None) -> str:
        """Send messages to GLM and return the text response.
        
        Args:
            messages: List of OpenAI-compatible message dicts.
                      e.g. [{"role": "system", "content": "..."},
                            {"role": "user", "content": [...]}]
            model_override: Override the default model for this call.
        
        Returns:
            The text content of the first choice's message.
        
        Raises:
            zai.APIStatusError: On API-level errors (4xx, 5xx)
            zai.APITimeoutError: On request timeout
            zai.APIConnectionError: On connection failures
        """
        import asyncio
        return await asyncio.to_thread(self.invoke_sync, messages, model_override)
    
    @property
    def provider(self) -> str:
        return "zhipuai"
