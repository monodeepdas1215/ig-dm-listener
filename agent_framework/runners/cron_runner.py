import asyncio
import logging
import os
import uuid
from pprint import pprint

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from langchain_core.messages import HumanMessage

from app.logging_config import configure_logging
from agent_framework.nodes.context import GraphContext
from agent_framework.runners.base_runner import BaseRunner

logger = logging.getLogger(__name__)

class CronRunner(BaseRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.compile_graphs()
        self.scheduler = AsyncIOScheduler()

    async def _execute_graph(self, graph_name: str, input_text: str):
        if graph_name not in self.registry:
            logger.error(f"Graph '{graph_name}' not found.")
            return

        request_id = str(uuid.uuid4())
        configure_logging(request_id)
        logger.info(f"Cron execution started for graph '{graph_name}' (Request ID: {request_id})")

        target_graph = self.registry[graph_name]
        initial_state = {"messages": [HumanMessage(content=input_text)]}
        config = {"configurable": {"thread_id": request_id, "request_id": request_id}}

        context = GraphContext(graph_name=graph_name)
        await context.initialize_context()

        try:
            async for event in target_graph.astream(initial_state, config=config, stream_mode="values"):
                pass  # Just execute
            
            final_state = await target_graph.aget_state(config)
            logger.info("Cron execution completed successfully.")
        except Exception as e:
            logger.error(f"Cron execution failed for '{graph_name}': {e}")

    async def start(self):
        cron_schedule = os.environ.get("CRON_SCHEDULE", "0 * * * *")  # Default hourly
        graph_name = os.environ.get("CRON_GRAPH_NAME", "insta-dm")
        input_text = os.environ.get("CRON_INPUT", "Triggered by cron")

        logger.info(f"Setting up cron schedule: {cron_schedule} for graph: {graph_name}")

        self.scheduler.add_job(
            self._execute_graph,
            trigger=CronTrigger.from_crontab(cron_schedule),
            args=[graph_name, input_text],
            id=f"cron_{graph_name}"
        )

        self.scheduler.start()
        logger.info("Cron scheduler started. Waiting for jobs...")

        try:
            # Keep the event loop running forever
            while True:
                await asyncio.sleep(3600)
        finally:
            self.scheduler.shutdown()
            await self.cleanup()
