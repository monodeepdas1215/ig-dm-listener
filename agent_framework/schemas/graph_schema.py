from enum import Enum
from pydantic import BaseModel, Field, model_validator


class NodeType(str, Enum):
    GRAPH_NODE = "graph-node"
    DEEPAGENT_NODE = "deepagent-node"
    INVOKE_GRAPH_NODE = "invoke-graph-node"


class CheckpointerType(str, Enum):
    MEMORY = "memory"
    SQLITE = "sqlite"


class EdgeCondition(BaseModel):
    handler: str                            # Dotted path to condition function
    description: str | None = None


class NodeDefinition(BaseModel):
    name: str
    type: NodeType
    path: str                               # Dotted path to BaseNode subclass
    target_graph: str | None = None         # Only for invoke-graph-node
    llm_ref: str | None = None              # Per-node LLM override

    @model_validator(mode="after")
    def validate_target_graph(self):
        if self.type == NodeType.INVOKE_GRAPH_NODE and not self.target_graph:
            raise ValueError("invoke-graph-node requires 'target_graph'")
        if self.type != NodeType.INVOKE_GRAPH_NODE and self.target_graph:
            raise ValueError("'target_graph' only valid for invoke-graph-node")
        return self


class EdgeDefinition(BaseModel):
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    condition: EdgeCondition | None = None


class GraphDefinition(BaseModel):
    name: str
    description: str | None = None
    llm_ref: str                            # Graph-level LLM reference
    state: str | None = None                # Dotted path to custom AgentState subclass
    checkpointer: CheckpointerType = CheckpointerType.MEMORY
    entry_point: str
    finish_point: str
    nodes: list[NodeDefinition]
    edges: list[EdgeDefinition]


class GraphsConfig(BaseModel):
    graphs: list[GraphDefinition]
