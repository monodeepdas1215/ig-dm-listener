import asyncio
import logging
import sqlite3
import uuid
import uvicorn
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from app.logging_config import configure_logging
from agent_framework.nodes.context import GraphContext
from agent_framework.runners.base_runner import BaseRunner

logger = logging.getLogger(__name__)

class RunRequest(BaseModel):
    input: str

class FastAPIRunner(BaseRunner):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db_path = "ig_dm_listener.db"
        self._init_db()
        self.compile_graphs()
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            yield
            await self.cleanup()
            
        self.app = FastAPI(title="Agent Framework API", lifespan=lifespan)
        self._setup_routes()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS run_states (
                    request_id TEXT PRIMARY KEY,
                    graph_name TEXT,
                    state TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def _update_run_state(self, request_id: str, state: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE run_states SET state = ? WHERE request_id = ?",
                (state, request_id)
            )
            conn.commit()

    def _create_run_record(self, request_id: str, graph_name: str, state: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO run_states (request_id, graph_name, state) VALUES (?, ?, ?)",
                (request_id, graph_name, state)
            )
            conn.commit()

    def _get_run_state(self, request_id: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT state FROM run_states WHERE request_id = ?", (request_id,))
            row = cursor.fetchone()
            if row:
                return row[0]
            return None

    async def _execute_graph(self, request_id: str, graph_name: str, input_text: str):
        configure_logging(request_id)
        logger.info(f"Executing graph '{graph_name}' in background (Request ID: {request_id})")
        
        target_graph = self.registry[graph_name]
        initial_state = {"messages": [HumanMessage(content=input_text)]}
        config = {"configurable": {"thread_id": request_id, "request_id": request_id}}
        
        context = GraphContext(graph_name=graph_name)
        await context.initialize_context()
        
        try:
            async for event in target_graph.astream(initial_state, config=config, stream_mode="values"):
                pass  # Just execute
            self._update_run_state(request_id, "COMPLETED")
            logger.info(f"Graph '{graph_name}' completed (Request ID: {request_id})")
        except Exception as e:
            logger.error(f"Graph '{graph_name}' failed: {e}")
            self._update_run_state(request_id, "FAILED")

    def _setup_routes(self):
        @self.app.post("/runs/{graph_name}")
        async def run_graph(graph_name: str, req: RunRequest, background_tasks: BackgroundTasks):
            if graph_name not in self.registry:
                raise HTTPException(status_code=404, detail=f"Graph '{graph_name}' not found.")
            
            request_id = str(uuid.uuid4())
            self._create_run_record(request_id, graph_name, "ONGOING")
            
            background_tasks.add_task(self._execute_graph, request_id, graph_name, req.input)
            return {"requestId": request_id}

        @self.app.get("/runs/{request_id}")
        async def get_run_status(request_id: str):
            state = self._get_run_state(request_id)
            if not state:
                raise HTTPException(status_code=404, detail="Run not found.")
            return {"lifecycleState": state}

    async def start(self):
        # We run the FastAPI server via uvicorn programmatically
        config = uvicorn.Config(app=self.app, host="0.0.0.0", port=8000, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
