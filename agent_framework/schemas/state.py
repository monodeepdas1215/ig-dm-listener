import operator
from enum import Enum
from typing import Annotated, Any
from langgraph.graph import MessagesState


class PipelineStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILURE = "FAILURE"


class AgentState(MessagesState):
    """Base state for all graphs. Extends LangGraph's MessagesState.

    Every custom graph state must inherit from AgentState:

        class DMAnalysisState(AgentState):
            dm_category: str = ""
            sentiment_score: float = 0.0
    """
    current_node: str = ""
    metadata: dict[str, Any] = {}
    errors: Annotated[list[str], operator.add] = []
    pipeline_status: str = PipelineStatus.SUCCESS.value
