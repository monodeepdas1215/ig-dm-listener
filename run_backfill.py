import asyncio
import logging
from pprint import pprint

from agent_framework.schemas.graph_schema import GraphsConfig
from agent_framework.schemas.llm_schema import LLMsConfig
from agent_framework.schemas.mcp_schema import McpConfig
from agent_framework.core.llm_loader import LLMLoader
from agent_framework.tools.mcp_loader import McpToolLoader
from agent_framework.core.graph_compiler import GraphCompiler
from app.logging_config import configure_logging
import json

def load_config(file_path: str, model_class):
    with open(file_path, "r") as f:
        data = json.load(f)
    return model_class.model_validate(data)

async def main():
    # Setup dedicated backfill log file
    configure_logging("backfill-reel-info")
    logger = logging.getLogger(__name__)
    
    config_dir = "agent_framework/config"
    
    graphs_config: GraphsConfig = load_config(f"{config_dir}/graphs.json", GraphsConfig)
    llms_config: LLMsConfig = load_config(f"{config_dir}/llms.conf", LLMsConfig)
    
    # Initialize Engine
    llm_loader = LLMLoader(llms_config)
    mcp_loader = McpToolLoader(config_path=f"{config_dir}/mcp.json")
    tool_loaders = [mcp_loader]

    compiler = GraphCompiler(llm_loader, tool_loaders)
    
    try:
        registry = compiler.compile_all(graphs_config)
    except Exception as e:
        logger.error(f"Failed to compile graphs: {e}")
        return

    graph_name = "backfill-reel-info"
    if graph_name not in registry:
        logger.error(f"Graph '{graph_name}' not found.")
        return

    target_graph = registry[graph_name]

    # Minimal initial state required to start the graph
    initial_state = {
        "messages": []
    }

    config = {"configurable": {"thread_id": "backfill_run_1"}}

    logger.info(f"Running graph '{graph_name}'...")
    
    try:
        async for event in target_graph.astream(initial_state, config=config, stream_mode="values"):
            pass
                
        # Get final state
        final_state = await target_graph.aget_state(config)
        logger.info("Final State Keys:")
        logger.info(list(final_state.values.keys()))
        
        report_path = final_state.values.get("backfill_report_path", "No report generated")
        logger.info(f"Finished. Report at: {report_path}")
        
    finally:
        await mcp_loader.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
