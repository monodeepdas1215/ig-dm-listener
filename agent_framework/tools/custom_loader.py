import inspect
from langchain_core.tools import BaseTool, tool
from agent_framework.tools.base import BaseToolLoader
from agent_framework.utils.import_utils import import_dotted_path

class CustomToolLoader(BaseToolLoader):
    """Loads custom Python tools by dotted import path.

    Tools must be decorated with @tool or be instances of BaseTool.

    Usage:
        loader = CustomToolLoader([
            "mypackage.tools.calculator",
            "mypackage.tools.formatter",
        ])
        tools = await loader.load_tools()
    """

    def __init__(self, tool_paths: list[str]):
        self.tool_paths = tool_paths

    async def load_tools(self) -> list[BaseTool]:
        tools = []
        for path in self.tool_paths:
            obj = import_dotted_path(path)
            
            # If it's already a BaseTool (like @tool decorators generate)
            if isinstance(obj, BaseTool):
                tools.append(obj)
            # If it's a function, wrap it with @tool
            elif inspect.isfunction(obj):
                tools.append(tool(obj))
            else:
                raise ValueError(f"Tool {path} must be a function or BaseTool")
                
        return tools

    async def cleanup(self) -> None:
        pass  # No resources to release
