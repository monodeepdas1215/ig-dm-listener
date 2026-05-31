from abc import ABC, abstractmethod
from langchain_core.tools import BaseTool


class BaseToolLoader(ABC):
    """Base interface for loading tools into the framework.

    Subclasses implement `load_tools()` to provide tools from
    different sources (MCP servers, custom Python functions, etc.).
    """

    @abstractmethod
    async def load_tools(self) -> list[BaseTool]:
        """Load and return available tools."""
        ...

    @abstractmethod
    async def cleanup(self) -> None:
        """Release resources (close MCP connections, etc.)."""
        ...
