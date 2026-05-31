class AgentFrameworkError(Exception):
    """Base exception for all agent framework errors."""

class ConfigValidationError(AgentFrameworkError):
    """Raised when JSON configuration files are invalid or fail schema validation."""

class LLMLoadError(AgentFrameworkError):
    """Raised when an LLM fails to load (e.g., missing API key, provider not found)."""

class NodeExecutionError(AgentFrameworkError):
    """Raised when a node encounters an error during execution."""

class GraphCompilationError(AgentFrameworkError):
    """Raised when graph compilation fails (e.g., missing nodes, circular dependencies, invalid edges)."""

class GraphNotFoundError(AgentFrameworkError):
    """Raised when a referenced graph does not exist in the registry."""

class ToolLoadError(AgentFrameworkError):
    """Raised when a tool fails to load."""

class RetryExhaustedError(AgentFrameworkError):
    """Raised when all retry attempts have been exhausted."""
    def __init__(self, message: str, last_exception: Exception | None = None, attempts: int = 0):
        super().__init__(message)
        self.last_exception = last_exception
        self.attempts = attempts
