import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from app.config import settings
from app.logging_config import configure_logging
from app.services.database import (
    init_db,
    close_pool,
    create_task_record,
    update_task_status,
    get_task_status,
    get_pending_tasks,
    fail_interrupted_tasks,
)
from agent_framework.nodes.context import GraphContext
from agent_framework.runners.base_runner import BaseRunner

logger = logging.getLogger(__name__)

class RunRequest(BaseModel):
    input: str

class FastAPIRunner(BaseRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.compile_graphs()
        
        self._queue = None
        self.concurrency_limit = settings.max_concurrent_workers
        self.workers = []
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Ensure the queue is bound to the lifespan's running event loop
            self._queue = None
            
            # Initialize Postgres tables
            await init_db()
            
            # Fail any tasks that were left running from a previous crash/shutdown
            try:
                interrupted = await fail_interrupted_tasks()
                if interrupted > 0:
                    logger.info(f"Marked {interrupted} interrupted tasks from previous run as FAILED.")
            except Exception as e:
                logger.error(f"Failed to fail interrupted tasks on startup: {e}")
                
            # Re-enqueue any PENDING tasks to the queue
            try:
                pending_tasks = await get_pending_tasks()
                for task in pending_tasks:
                    await self.queue.put({
                        "task_id": task["task_id"],
                        "graph_name": task["graph_name"],
                        "input_text": task["input_text"],
                    })
                if pending_tasks:
                    logger.info(f"Re-enqueued {len(pending_tasks)} pending tasks to the worker pool queue.")
            except Exception as e:
                logger.error(f"Failed to recover pending tasks on startup: {e}")
            
            # Start background workers
            self.workers = [
                asyncio.create_task(self._worker_loop(i))
                for i in range(self.concurrency_limit)
            ]
            logger.info(f"Started {self.concurrency_limit} background queue workers.")
            
            yield
            
            # Shutdown: Cancel workers and wait for them to finish cleanly
            logger.info("Stopping background queue workers...")
            for worker in self.workers:
                worker.cancel()
            
            if self.workers:
                await asyncio.gather(*self.workers, return_exceptions=True)
                
            await close_pool()
            await self.cleanup()
            logger.info("Lifespan shutdown complete.")
            
        self.app = FastAPI(title="Agent Framework API", lifespan=lifespan)
        self._setup_routes()

    @property
    def queue(self) -> asyncio.Queue:
        if self._queue is None:
            self._queue = asyncio.Queue()
        return self._queue

    async def _worker_loop(self, worker_id: int):
        logger.info(f"Worker-{worker_id} loop started.")
        while True:
            try:
                task_data = await self.queue.get()
                task_id = task_data["task_id"]
                graph_name = task_data["graph_name"]
                input_text = task_data["input_text"]
                
                logger.info(f"Worker-{worker_id} processing task {task_id} ({graph_name})")
                
                # 1. Update task to RUNNING in database
                await update_task_status(task_id, "RUNNING", started_at=datetime.now(timezone.utc))
                
                # 2. Execute graph
                try:
                    await self._execute_graph(task_id, graph_name, input_text)
                    # 3. Update task to COMPLETED in database
                    await update_task_status(task_id, "COMPLETED", completed_at=datetime.now(timezone.utc))
                    logger.info(f"Worker-{worker_id} completed task {task_id} successfully.")
                except Exception as e:
                    logger.error(f"Worker-{worker_id} failed task {task_id}: {e}")
                    # 4. Update task to FAILED in database with error message
                    await update_task_status(
                        task_id,
                        "FAILED",
                        completed_at=datetime.now(timezone.utc),
                        error_message=str(e),
                    )
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                logger.info(f"Worker-{worker_id} received cancel request. Shutting down.")
                break
            except Exception as e:
                logger.error(f"Worker-{worker_id} encountered unhandled exception in loop: {e}")
                await asyncio.sleep(1)

    async def _execute_graph(self, request_id: str, graph_name: str, input_text: str):
        configure_logging(request_id)
        logger.info(f"Executing graph '{graph_name}' (Request ID: {request_id})")
        
        target_graph = self.registry[graph_name]
        initial_state = {"messages": [HumanMessage(content=input_text)]}
        config = {"configurable": {"thread_id": request_id, "request_id": request_id}}
        
        context = GraphContext(graph_name=graph_name)
        await context.initialize_context()
        
        # We propagate any exception out so the worker loop can handle status updates
        async for event in target_graph.astream(initial_state, config=config, stream_mode="values"):
            pass  # Just execute
        logger.info(f"Graph '{graph_name}' execution finished (Request ID: {request_id})")

    def _setup_routes(self):
        @self.app.post("/runs/{graph_name}")
        async def run_graph(graph_name: str, req: RunRequest):
            if graph_name not in self.registry:
                raise HTTPException(status_code=404, detail=f"Graph '{graph_name}' not found.")
            
            request_id = str(uuid.uuid4())
            # Persistent queue tracking: store task as PENDING in PostgreSQL
            await create_task_record(request_id, graph_name, req.input)
            
            # Enqueue task in-memory for workers
            await self.queue.put({
                "task_id": request_id,
                "graph_name": graph_name,
                "input_text": req.input,
            })
            
            return {"requestId": request_id}

        @self.app.get("/runs/{request_id}")
        async def get_run_status(request_id: str):
            state = await get_task_status(request_id)
            if not state:
                raise HTTPException(status_code=404, detail="Run not found.")
            
            # Map database state for backward compatibility
            if state in ("PENDING", "RUNNING"):
                state = "ONGOING"
            return {"lifecycleState": state}

    async def start(self):
        # We run the FastAPI server via uvicorn programmatically
        config = uvicorn.Config(app=self.app, host="0.0.0.0", port=8000, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
