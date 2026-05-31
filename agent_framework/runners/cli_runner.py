import argparse
import logging
import uuid
from pprint import pprint

from langchain_core.messages import HumanMessage

from app.logging_config import configure_logging
from agent_framework.nodes.context import GraphContext
from agent_framework.runners.base_runner import BaseRunner

logger = logging.getLogger(__name__)

class CLIRunner(BaseRunner):
    async def start(self):
        parser = argparse.ArgumentParser(description="Agent Framework CLI Runner")
        parser.add_argument("--graph", type=str, help="Name of the graph to run")
        parser.add_argument("--input", type=str, help="Input message to the graph")
        parser.add_argument("--list", action="store_true", help="List available graphs")
        parser.add_argument("--validate", action="store_true", help="Validate all config files")

        args = parser.parse_args()

        if args.validate:
            logger.info("All configuration files validated successfully.")
            return

        if args.list:
            logger.info("Available graphs:")
            for g in self.graphs_config.graphs:
                logger.info(f" - {g.name}: {g.description}")
            return

        if not args.graph or not args.input:
            parser.print_help()
            return

        self.compile_graphs()

        if args.graph not in self.registry:
            logger.error(f"Graph '{args.graph}' not found.")
            return

        target_graph = self.registry[args.graph]

        # Generate Request ID for Logging
        request_id = str(uuid.uuid4())
        configure_logging(request_id)
        logger.info(f"Generated Request ID: {request_id}")

        # Create initial state
        initial_state = {
            "messages": [HumanMessage(content=args.input)]
        }

        config = {"configurable": {"thread_id": request_id, "request_id": request_id}}

        logger.info(f"Running graph '{args.graph}'...")
        
        # Initialize Context before running Graph
        context = GraphContext(graph_name=args.graph)
        await context.initialize_context()
        
        try:
            async for event in target_graph.astream(initial_state, config=config, stream_mode="values"):
                messages = event.get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    print(f"[{last_msg.type.upper()}]: {last_msg.content[:200]}...")
                    
            final_state = await target_graph.aget_state(config)
            logger.info("Final State:")
            pprint(final_state.values)
        finally:
            await self.cleanup()
