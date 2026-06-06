from dataclasses import dataclass, field
from typing import Any
from agent_framework.tools.base import BaseToolLoader


@dataclass(frozen=True)
class GraphContext:
    """Context injected into every BaseNode at init time.

    Provides the node with access to the graph's LLM, tool loaders,
    and the compiled graph registry (for invoke-graph-node).
    """
    llm: Any = None
    llm_provider: str | None = None
    tool_loaders: list[BaseToolLoader] = field(default_factory=list)
    graph_registry: dict = field(default_factory=dict)
    graph_name: str = ""
    node_name: str = ""

    async def initialize_context(self):
        import logging
        from app.config import settings
        from app.services.database import init_db, ensure_db
        
        logger = logging.getLogger(__name__)
        if getattr(settings, "drop_db_on_start", False):
            logger.info("drop_db_on_start is True: running init_db (dropping existing data).")
            await init_db()
        else:
            logger.info("drop_db_on_start is False: running ensure_db (preserving existing data).")
            await ensure_db()
