from enum import Enum
from pydantic import BaseModel


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE_GENAI = "google-genai"
    OLLAMA = "ollama"
    ZHIPUAI = "zhipuai"

    def is_glm(self) -> bool:
        """Returns True for ZhipuAI/GLM providers that use native SDK."""
        return self == LLMProvider.ZHIPUAI

class LLMParameters(BaseModel):
    temperature: float = 0.15
    max_tokens: int | None = None
    top_p: float | None = None
    timeout: int | None = None
    max_retries: int = 0

class LLMConfig(BaseModel):
    name: str
    provider: LLMProvider
    model: str
    api_key_env: str
    parameters: LLMParameters = LLMParameters()
    base_url: str | None = None
    organization: str | None = None
    extra_model_kwargs: dict | None = None

class LLMsConfig(BaseModel):
    llms: list[LLMConfig]
