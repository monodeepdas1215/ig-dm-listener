from agent_framework.nodes.base import BaseNode
from agent_framework.nodes.context import GraphContext
from agent_framework.schemas.graph_schema import NodeDefinition
from agent_framework.utils.import_utils import import_dotted_path
from agent_framework.exceptions import GraphCompilationError


class NodeFactory:
    """Creates node instances from graph definitions."""

    @staticmethod
    def create(node_def: NodeDefinition, context: GraphContext) -> BaseNode:
        # 1. Import the node class from dotted path
        try:
            node_class = import_dotted_path(node_def.path)
        except Exception as e:
            raise GraphCompilationError(f"Failed to import node class '{node_def.path}': {e}")

        # 2. Validate it's a BaseNode subclass
        if not issubclass(node_class, BaseNode):
            raise GraphCompilationError(
                f"Node '{node_def.path}' must be a subclass of BaseNode"
            )

        # 3. Instantiate with context
        try:
            return node_class(context)
        except Exception as e:
            raise GraphCompilationError(f"Failed to instantiate node '{node_def.path}': {e}")
