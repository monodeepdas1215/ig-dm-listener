from typing import Dict, Any
import logging
from langgraph.graph import StateGraph, START, END
from agent_framework.schemas.graph_schema import GraphsConfig, GraphDefinition
from agent_framework.schemas.state import AgentState
from agent_framework.core.llm_loader import LLMLoader
from agent_framework.core.checkpointer import CheckpointerFactory
from agent_framework.core.node_factory import NodeFactory
from agent_framework.nodes.context import GraphContext
from agent_framework.tools.base import BaseToolLoader
from agent_framework.utils.import_utils import import_dotted_path
from agent_framework.exceptions import GraphCompilationError

logger = logging.getLogger(__name__)


class GraphCompiler:
    """Compiles JSON graph definitions into LangGraph StateGraphs."""

    def __init__(self, llm_loader: LLMLoader, tool_loaders: list[BaseToolLoader]):
        self.llm_loader = llm_loader
        self.tool_loaders = tool_loaders
        self.registry: Dict[str, Any] = {}

    def compile_all(self, config: GraphsConfig) -> Dict[str, Any]:
        """Compile all graphs, respecting dependencies (invoke-graph-node)."""
        # Build dependency graph
        dependencies = {g.name: set() for g in config.graphs}
        graph_by_name = {g.name: g for g in config.graphs}
        
        for g in config.graphs:
            for node in g.nodes:
                if node.target_graph:
                    if node.target_graph not in graph_by_name:
                        raise GraphCompilationError(f"Graph '{g.name}' depends on unknown graph '{node.target_graph}'")
                    dependencies[g.name].add(node.target_graph)

        # Topological sort
        ordered_graphs = []
        visited = set()
        temp_visited = set()

        def visit(name: str):
            if name in temp_visited:
                raise GraphCompilationError(f"Circular dependency detected involving graph '{name}'")
            if name not in visited:
                temp_visited.add(name)
                for dep in dependencies[name]:
                    visit(dep)
                temp_visited.remove(name)
                visited.add(name)
                ordered_graphs.append(graph_by_name[name])

        for g in config.graphs:
            if g.name not in visited:
                visit(g.name)

        # Compile in order
        for graph_def in ordered_graphs:
            self.registry[graph_def.name] = self._compile_graph(graph_def)

        return self.registry

    def _compile_graph(self, graph_def: GraphDefinition) -> Any:
        logger.info(f"Compiling graph: {graph_def.name}")
        
        # 1. Resolve State Class
        if graph_def.state:
            try:
                state_class = import_dotted_path(graph_def.state)
                try:
                    if not issubclass(state_class, AgentState):
                        raise GraphCompilationError(f"State class '{graph_def.state}' must extend AgentState")
                except TypeError:
                    # TypedDicts do not support issubclass
                    required_fields = set(getattr(AgentState, "__annotations__", {}).keys())
                    provided_fields = set(getattr(state_class, "__annotations__", {}).keys())
                    if not required_fields.issubset(provided_fields):
                        missing = required_fields - provided_fields
                        raise GraphCompilationError(f"State class '{graph_def.state}' is missing AgentState fields: {missing}")
            except GraphCompilationError:
                raise
            except Exception as e:
                raise GraphCompilationError(f"Failed to load state class '{graph_def.state}': {e}")
        else:
            state_class = AgentState

        # 2. Builder
        builder = StateGraph(state_class)

        # 3. Context
        llm = None
        llm_provider = None
        if graph_def.llm_ref:
            llm = self.llm_loader.get_llm(graph_def.llm_ref)
            llm_provider = self.llm_loader.get_provider(graph_def.llm_ref)
            
        context = GraphContext(
            llm=llm,
            llm_provider=llm_provider,
            tool_loaders=self.tool_loaders,
            graph_registry=self.registry,
            graph_name=graph_def.name
        )

        # 4. Add Nodes
        for node_def in graph_def.nodes:
            # Resolve per-node LLM (if configured) or fall back to graph-level
            node_llm = context.llm
            node_llm_provider = context.llm_provider
            if node_def.llm_ref:
                node_llm = self.llm_loader.get_llm(node_def.llm_ref)
                node_llm_provider = self.llm_loader.get_provider(node_def.llm_ref)

            node_context = GraphContext(
                llm=node_llm,
                llm_provider=node_llm_provider,
                tool_loaders=context.tool_loaders,
                graph_registry=context.graph_registry,
                graph_name=context.graph_name,
                node_name=node_def.name
            )
            node_instance = NodeFactory.create(node_def, node_context)
            builder.add_node(node_def.name, node_instance.run)

        # 5. Add Edges
        # Entry point
        builder.add_edge(START, graph_def.entry_point)

        # Explicit edges
        conditional_edges_by_source = {}
        for edge_def in graph_def.edges:
            if edge_def.condition:
                if edge_def.from_node not in conditional_edges_by_source:
                    conditional_edges_by_source[edge_def.from_node] = []
                conditional_edges_by_source[edge_def.from_node].append(edge_def)
            else:
                builder.add_edge(edge_def.from_node, edge_def.to_node)

        for source, edges in conditional_edges_by_source.items():
            def make_router(edges_for_source):
                # Pre-load condition functions to avoid importing on every invocation
                handlers = []
                for edge in edges_for_source:
                    try:
                        cond_fn = import_dotted_path(edge.condition.handler)
                        handlers.append((cond_fn, edge.to_node))
                    except Exception as e:
                        raise GraphCompilationError(f"Failed to load condition '{edge.condition.handler}': {e}")
                
                def router(state):
                    destinations = []
                    for cond_fn, to_node in handlers:
                        if cond_fn(state):
                            destinations.append(to_node)
                    # If no conditions matched, route to END
                    return destinations if destinations else END
                return router
                
            builder.add_conditional_edges(source, make_router(edges))

        # Finish point
        builder.add_edge(graph_def.finish_point, END)

        # 6. Compile with Checkpointer
        checkpointer = CheckpointerFactory.create(graph_def.checkpointer, graph_def.name)
        compiled_graph = builder.compile(checkpointer=checkpointer)

        return compiled_graph
