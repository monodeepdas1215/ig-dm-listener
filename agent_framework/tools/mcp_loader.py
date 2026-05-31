import json
import logging
from typing import Dict, List, Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from langchain_core.tools import BaseTool, tool
from agent_framework.tools.base import BaseToolLoader

logger = logging.getLogger(__name__)


class McpToolLoader(BaseToolLoader):
    """Loads tools from MCP servers.

    Reads mcp.json config, connects to each server (stdio or SSE),
    discovers available tools via the MCP protocol, and wraps them
    as LangChain BaseTool instances.
    """

    def __init__(self, config_path: str = "agent_framework/config/mcp.json"):
        self.config_path = config_path
        self._sessions: Dict[str, ClientSession] = {}
        self._exit_stacks = []

    async def _init_sessions(self):
        """Initialize sessions if not already done."""
        if self._sessions:
            return

        import asyncio
        from contextlib import AsyncExitStack
        
        try:
            with open(self.config_path, "r") as f:
                config_data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load MCP config {self.config_path}: {e}")
            return

        servers = config_data.get("mcpServers", {})
        
        for name, conf in servers.items():
            try:
                stack = AsyncExitStack()
                self._exit_stacks.append(stack)

                if "command" in conf:
                    # Stdio client
                    server_params = StdioServerParameters(
                        command=conf["command"],
                        args=conf.get("args", []),
                        env=conf.get("env", None)
                    )
                    transport, _ = await stack.enter_async_context(stdio_client(server_params))
                elif "url" in conf:
                    # SSE client
                    url = conf["url"]
                    headers = conf.get("headers", {})
                    transport, _ = await stack.enter_async_context(sse_client(url, headers=headers))
                else:
                    logger.warning(f"Invalid MCP server config for '{name}'")
                    continue

                session = await stack.enter_async_context(ClientSession(transport, transport))
                await session.initialize()
                self._sessions[name] = session
            except Exception as e:
                logger.error(f"Failed to connect to MCP server '{name}': {e}")

    def _wrap_mcp_tool(self, server_name: str, mcp_tool: Any, session: ClientSession) -> BaseTool:
        """Wrap an MCP tool as a LangChain tool."""
        # Simple dynamic wrapper creation.
        # DeepAgent/LangChain can consume standard callable tools
        
        async def mcp_tool_wrapper(**kwargs):
            try:
                result = await session.call_tool(mcp_tool.name, arguments=kwargs)
                return result
            except Exception as e:
                return f"Error calling tool {mcp_tool.name}: {e}"
        
        mcp_tool_wrapper.__name__ = mcp_tool.name
        mcp_tool_wrapper.__doc__ = mcp_tool.description
        
        # We use the @tool decorator to automatically convert it to a BaseTool subclass.
        return tool(mcp_tool_wrapper)

    async def load_tools(self) -> list[BaseTool]:
        """Load tools from all initialized MCP servers."""
        await self._init_sessions()
        
        tools = []
        for server_name, session in self._sessions.items():
            try:
                response = await session.list_tools()
                for t in response.tools:
                    tools.append(self._wrap_mcp_tool(server_name, t, session))
            except Exception as e:
                logger.error(f"Error fetching tools from {server_name}: {e}")
        return tools

    async def cleanup(self) -> None:
        """Close all MCP sessions."""
        import asyncio
        for stack in self._exit_stacks:
            try:
                await stack.aclose()
            except Exception as e:
                logger.error(f"Error cleaning up MCP session: {e}")
        self._sessions.clear()
        self._exit_stacks.clear()
