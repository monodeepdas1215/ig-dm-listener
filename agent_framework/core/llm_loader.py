import os
import logging
from typing import Dict
from langchain_core.language_models import BaseChatModel
from agent_framework.schemas.llm_schema import LLMConfig, LLMProvider, LLMsConfig
from agent_framework.exceptions import LLMLoadError

logger = logging.getLogger(__name__)


class LLMLoader:
    """Loads and caches LLM instances from configuration."""

    def __init__(self, config: LLMsConfig):
        self.config = config
        self._cache: Dict[str, BaseChatModel] = {}
        self._configs: Dict[str, LLMConfig] = {llm.name: llm for llm in config.llms}

    def get_llm(self, name: str) -> BaseChatModel:
        """Get an instantiated LLM by name."""
        if name in self._cache:
            return self._cache[name]

        if name not in self._configs:
            raise LLMLoadError(f"LLM '{name}' not found in configuration")

        llm_config = self._configs[name]
        api_key = self._resolve_api_key(llm_config.api_key_env)
        
        try:
            llm = self._instantiate_llm(llm_config, api_key)
            self._cache[name] = llm
            return llm
        except Exception as e:
            raise LLMLoadError(f"Failed to instantiate LLM '{name}': {e}")

    def _resolve_api_key(self, api_key_env: str) -> str:
        """Resolve API key from environment variable reference."""
        # e.g., "${OPENAI_API_KEY}" -> "OPENAI_API_KEY"
        if api_key_env.startswith("${") and api_key_env.endswith("}"):
            env_var = api_key_env[2:-1]
            val = os.getenv(env_var)
            if not val:
                raise LLMLoadError(f"Environment variable '{env_var}' not set")
            return val
        # Fallback if it's just the plain var name
        val = os.getenv(api_key_env)
        if not val:
            raise LLMLoadError(f"Environment variable '{api_key_env}' not set")
        return val

    def _instantiate_llm(self, config: LLMConfig, api_key: str) -> BaseChatModel:
        """Create LangChain ChatModel based on provider."""
        params = config.parameters.model_dump(exclude_none=True)

        if config.provider == LLMProvider.OPENAI:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=config.model,
                api_key=api_key,
                base_url=config.base_url,
                organization=config.organization,
                **params
            )
        elif config.provider == LLMProvider.ANTHROPIC:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=config.model,
                api_key=api_key,
                **params
            )
        elif config.provider == LLMProvider.GOOGLE_GENAI:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=config.model,
                api_key=api_key,
                **params
            )
        elif config.provider == LLMProvider.OLLAMA:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=config.model,
                api_key=api_key or "ollama",
                base_url=config.base_url or "http://localhost:11434/v1",
                **params
            )
        else:
            raise LLMLoadError(f"Unsupported provider: {config.provider}")
