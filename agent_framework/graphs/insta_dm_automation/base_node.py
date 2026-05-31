from agent_framework.nodes.base import BaseNode
from agent_framework.nodes.context import GraphContext
from agent_framework.utils.prompts import LLMUtils


class InstaDMBaseNode(BaseNode):
    """Base node for all Insta DM automation nodes."""

    def __init__(self, context: GraphContext):
        super().__init__(context)
        self.prompt = LLMUtils
