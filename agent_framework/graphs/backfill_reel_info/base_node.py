from agent_framework.nodes.base import BaseNode
from agent_framework.nodes.context import GraphContext
from agent_framework.utils.prompts import LLMUtils

class BackfillBaseNode(BaseNode):
    def __init__(self, context: GraphContext):
        super().__init__(context)
        self.prompt = LLMUtils
