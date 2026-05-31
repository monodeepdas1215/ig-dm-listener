from enum import Enum
from pydantic import BaseModel


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE_GENAI = "google-genai"
    OLLAMA = "ollama"

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

class LLMsConfig(BaseModel):
    llms: list[LLMConfig]
