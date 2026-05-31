import json
import logging
import sys
from typing import Dict, Any
from abc import ABC, abstractmethod

from agent_framework.schemas.graph_schema import GraphsConfig
from agent_framework.schemas.llm_schema import LLMsConfig
from agent_framework.schemas.mcp_schema import McpConfig
from agent_framework.core.llm_loader import LLMLoader
from agent_framework.tools.mcp_loader import McpToolLoader
from agent_framework.core.graph_compiler import GraphCompiler

logger = logging.getLogger(__name__)

class BaseRunner(ABC):
    def __init__(self, config_dir: str = "agent_framework/config"):
        self.config_dir = config_dir
        self.graphs_config: GraphsConfig = self._load_config(f"{config_dir}/graphs.json", GraphsConfig)
        self.llms_config: LLMsConfig = self._load_config(f"{config_dir}/llms.conf", LLMsConfig)
        self.mcp_config: McpConfig = self._load_config(f"{config_dir}/mcp.json", McpConfig)
        
        # Loaders
        self.llm_loader = LLMLoader(self.llms_config)
        self.mcp_loader = McpToolLoader(config_path=f"{config_dir}/mcp.json")
        self.tool_loaders = [self.mcp_loader]
        
        self.compiler = GraphCompiler(self.llm_loader, self.tool_loaders)
        self.registry: Dict[str, Any] = {}

    def _load_config(self, file_path: str, model_class):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            return model_class.model_validate(data)
        except Exception as e:
            logger.error(f"Failed to load/validate {file_path}: {e}")
            sys.exit(1)

    def compile_graphs(self):
        try:
            self.registry = self.compiler.compile_all(self.graphs_config)
            logger.info("Graphs compiled successfully.")
        except Exception as e:
            logger.error(f"Failed to compile graphs: {e}")
            sys.exit(1)

    async def cleanup(self):
        await self.mcp_loader.cleanup()

    @abstractmethod
    async def start(self):
        """Start the runner."""
        pass
