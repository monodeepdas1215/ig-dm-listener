from pydantic import BaseModel


class StdioMcpServer(BaseModel):
    """MCP server launched as subprocess via command + args."""
    command: str
    args: list[str] = []
    env: dict[str, str] = {}


class SseMcpServer(BaseModel):
    """Remote MCP server connected via SSE/HTTP."""
    url: str
    transport: str = "sse"
    headers: dict[str, str] = {}


class McpServerConfig(BaseModel):
    """Union of stdio and SSE server configs — discriminated by presence of 'command' vs 'url'."""
    command: str | None = None
    args: list[str] = []
    url: str | None = None
    transport: str = "sse"
    env: dict[str, str] = {}
    headers: dict[str, str] = {}


class McpConfig(BaseModel):
    mcpServers: dict[str, McpServerConfig] = {}
