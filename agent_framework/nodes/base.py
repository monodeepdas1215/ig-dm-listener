from abc import ABC, abstractmethod
from agent_framework.nodes.context import GraphContext
from agent_framework.schemas.state import AgentState
from agent_framework.tools.base import BaseToolLoader


class BaseNode(ABC):
    """Abstract base for all graph nodes.

    Interface contract:
        __init__(context) — receive framework resources (LLM, tools, registry)
        run(state)        — execute node logic, return partial state updates
    """

    def __init__(self, context: GraphContext):
        self.context = context
        self.llm = context.llm
        self.tool_loaders = context.tool_loaders
        self.graph_registry = context.graph_registry

    @abstractmethod
    async def run(self, state: AgentState) -> dict:
        """Execute node logic and return partial state updates.

        Args:
            state: Current graph state (AgentState or subclass).

        Returns:
            Dict of state keys to update. Only include changed keys.
        """
        ...

    def _find_loader(self, loader_type: type) -> BaseToolLoader | None:
        """Find a specific tool loader by type."""
        for loader in self.tool_loaders:
            if isinstance(loader, loader_type):
                return loader
        return None
