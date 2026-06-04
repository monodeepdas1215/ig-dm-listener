import json
import logging
from typing import Dict, List, Any
import httpx
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from agent_framework.tools.base import BaseToolLoader

logger = logging.getLogger(__name__)


class McpToolLoader(BaseToolLoader):
    """Loads tools from MCP servers.

    Reads mcp.json config, connects to each server using MultiServerMCPClient,
    and returns them as LangChain BaseTool instances.
    """

    def __init__(self, config_path: str = "agent_framework/config/mcp.json"):
        self.config_path = config_path
        self._client: MultiServerMCPClient | None = None

    def _build_server_configs(self) -> dict:
        """Parse mcp.json into MultiServerMCPClient config format."""
        try:
            with open(self.config_path, "r") as f:
                config_data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load MCP config {self.config_path}: {e}")
            return {}

        servers = {}
        for name, conf in config_data.get("mcpServers", {}).items():
            if "command" in conf:
                servers[name] = {
                    "transport": "stdio",
                    "command": conf["command"],
                    "args": conf.get("args", []),
                    "env": conf.get("env", None),
                }
            elif conf.get("type") == "http" or "url" in conf:
                transport = "streamable_http" if conf.get("type") == "http" else "sse"
                servers[name] = {
                    "transport": transport,
                    "url": conf["url"],
                    "headers": conf.get("headers", {}),
                    "httpx_client_factory": self._make_httpx_factory(),
                }
        return servers

    @staticmethod
    def _make_httpx_factory():
        """Factory for httpx client that bypasses self-signed SSL certs."""
        def factory(headers=None, timeout=None, auth=None):
            return httpx.AsyncClient(
                verify=False,
                headers=headers,
                timeout=timeout,
                auth=auth,
            )
        return factory

    async def load_tools(self) -> list[BaseTool]:
        """Load tools from all configured MCP servers."""
        if self._client is not None:
            return await self._client.get_tools()

        configs = self._build_server_configs()
        if not configs:
            return []

        try:
            self._client = MultiServerMCPClient(configs)
            tools = await self._client.get_tools()
            return tools
        except Exception as e:
            logger.error(f"Failed to load MCP tools: {e}")
            return []

    async def cleanup(self) -> None:
        """Clean up the client."""
        self._client = None
