import asyncio
import os
import uuid
import logging
from datetime import datetime, timezone
import asyncpg
from fastapi.testclient import TestClient

# Configure logging for test output
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_fastapi_runner")

# Set test environment database
TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://igapp:igapp_secret@localhost:5432/ig_dm_listener",
)
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["DROP_DB_ON_START"] = "false"  # Manually managed by the test, do not drop on every graph context init
os.environ["MAX_CONCURRENT_WORKERS"] = "2"  # Set concurrency limit to 2 for testing limits

from app.config import settings
from app.services.database import get_pool, get_task_status
import app.services.database
from agent_framework.runners.fastapi_runner import FastAPIRunner

# A dummy Graph class that mimics a LangGraph runnable
class DummyGraph:
    def __init__(self, execution_delay: float = 0.5, fail: bool = False):
        self.execution_delay = execution_delay
        self.fail = fail

    async def astream(self, initial_state, config, stream_mode="values"):
        logger.info(f"DummyGraph execution started (delay: {self.execution_delay}s)...")
        await asyncio.sleep(self.execution_delay)
        if self.fail:
            raise ValueError("Simulated graph execution failure")
        yield {"messages": []}
        logger.info("DummyGraph execution completed.")


async def cleanup_db():
    # Reset pool variable to ensure we connect on the current loop
    app.services.database._pool = None
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS task_details")
        await conn.execute("DROP TABLE IF EXISTS reel_analysis")
    await pool.close()
    app.services.database._pool = None
    logger.info("Database cleaned up.")


async def run_integration_tests():
    logger.info("--- Starting FastAPIRunner Integration Tests ---")
    
    # 1. Reset/drop tables once before starting runner
    app.services.database._pool = None
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS task_details")
        await conn.execute("DROP TABLE IF EXISTS reel_analysis")
    await pool.close()
    app.services.database._pool = None
    logger.info("Manually dropped tables for clean startup.")

    # 2. Initialize runner and override graphs in registry with dummy graphs
    runner = FastAPIRunner()
    runner.registry = {
        "insta-dm-automation": DummyGraph(execution_delay=0.4),
        "failing-graph": DummyGraph(execution_delay=0.1, fail=True),
    }

    # Use TestClient with lifespan context manager to run startup/shutdown logic
    with TestClient(runner.app) as client:
        # Test Case 1: Single Task Successful Run
        logger.info("[Test 1] Dispatching a single successful graph run...")
        response = client.post("/runs/insta-dm-automation", json={"input": "Test Input 1"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        request_id = response.json()["requestId"]
        logger.info(f"Dispatched task ID: {request_id}")

        # Check status immediately (should be ONGOING / PENDING)
        status_resp = client.get(f"/runs/{request_id}")
        assert status_resp.status_code == 200
        state = status_resp.json()["lifecycleState"]
        assert state == "ONGOING", f"Expected state to be ONGOING, got {state}"

        # Wait for completion
        await asyncio.sleep(0.6)
        
        status_resp = client.get(f"/runs/{request_id}")
        state = status_resp.json()["lifecycleState"]
        assert state == "COMPLETED", f"Expected state to be COMPLETED, got {state}"
        logger.info("✅ Test 1 Passed: Single task completed successfully.")

        # Test Case 2: Task Failure Handling
        logger.info("[Test 2] Dispatching a failing graph run...")
        response = client.post("/runs/failing-graph", json={"input": "Fail Input"})
        assert response.status_code == 200
        fail_request_id = response.json()["requestId"]

        await asyncio.sleep(0.3)

        # Check status
        status_resp = client.get(f"/runs/{fail_request_id}")
        state = status_resp.json()["lifecycleState"]
        assert state == "FAILED", f"Expected state to be FAILED, got {state}"
        
        # Verify the exception message is stored in the database
        # Reset pool global variable so we can query on this test runner loop
        app.services.database._pool = None
        db_state = await get_task_status(fail_request_id)
        assert db_state == "FAILED"
        pool = await get_pool()
        async with pool.acquire() as conn:
            err_msg = await conn.fetchval("SELECT error_message FROM task_details WHERE task_id = $1", fail_request_id)
            assert "Simulated graph execution failure" in err_msg
        await pool.close()
        app.services.database._pool = None
        
        logger.info("✅ Test 2 Passed: Failing task was handled correctly and error persisted.")

        # Test Case 3: Concurrency Bound (Queueing)
        logger.info("[Test 3] Testing concurrency bounds (limit = 2). Sending 5 tasks...")
        # Create a slow graph to hold workers
        runner.registry["slow-graph"] = DummyGraph(execution_delay=0.6)
        
        task_ids = []
        for i in range(5):
            resp = client.post("/runs/slow-graph", json={"input": f"Concurrent {i}"})
            task_ids.append(resp.json()["requestId"])
        
        # Allow workers a small moment to dequeue the first two
        await asyncio.sleep(0.15)

        # Query states from the database directly to verify their queue states
        app.services.database._pool = None
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT task_id, status FROM task_details WHERE task_id = ANY($1)", task_ids)
            states = {row["task_id"]: row["status"] for row in rows}
        await pool.close()
        app.services.database._pool = None
            
        running_count = sum(1 for status in states.values() if status == "RUNNING")
        pending_count = sum(1 for status in states.values() if status == "PENDING")
        
        logger.info(f"Database states for concurrent tasks: {states}")
        logger.info(f"Running: {running_count}, Pending: {pending_count}")
        
        # With max_concurrent_workers = 2, only 2 should be running, 3 pending.
        assert running_count == 2, f"Expected 2 running, got {running_count}"
        assert pending_count == 3, f"Expected 3 pending, got {pending_count}"
        
        # Wait for all of them to finish
        await asyncio.sleep(1.8)
        
        for tid in task_ids:
            status_resp = client.get(f"/runs/{tid}")
            assert status_resp.json()["lifecycleState"] == "COMPLETED"
        logger.info("✅ Test 3 Passed: Concurrency limit respected and all tasks eventually completed.")

    # Test Case 4: Crash Recovery on Lifespan Startup
    logger.info("[Test 4] Testing startup crash recovery...")
    # Inject directly into the DB: one RUNNING task (simulating crash) and one PENDING task
    crashed_task_id = str(uuid.uuid4())
    pending_task_id = str(uuid.uuid4())
    
    app.services.database._pool = None
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO task_details (task_id, graph_name, input_text, status, created_at) VALUES ($1, $2, $3, $4, NOW())",
            crashed_task_id, "insta-dm-automation", "Crashed task", "RUNNING"
        )
        await conn.execute(
            "INSERT INTO task_details (task_id, graph_name, input_text, status, created_at) VALUES ($1, $2, $3, $4, NOW())",
            pending_task_id, "insta-dm-automation", "Pending task", "PENDING"
        )
    await pool.close()
    app.services.database._pool = None
    logger.info("Injected crashed (RUNNING) and pending (PENDING) tasks directly into the database.")

    # Re-run TestClient lifespan to trigger startup crash recovery
    with TestClient(runner.app) as client:
        # Give the worker pool a brief moment to process
        await asyncio.sleep(0.6)

        # The previously RUNNING task should now be marked as FAILED with error message
        status_resp = client.get(f"/runs/{crashed_task_id}")
        assert status_resp.json()["lifecycleState"] == "FAILED"
        
        app.services.database._pool = None
        pool = await get_pool()
        async with pool.acquire() as conn:
            err_msg = await conn.fetchval("SELECT error_message FROM task_details WHERE task_id = $1", crashed_task_id)
            assert "interrupted" in err_msg.lower()
        await pool.close()
        app.services.database._pool = None
            
        # The previously PENDING task should have been re-enqueued and successfully executed
        status_resp = client.get(f"/runs/{pending_task_id}")
        assert status_resp.json()["lifecycleState"] == "COMPLETED"
        logger.info("✅ Test 4 Passed: Crashed task marked FAILED, pending task recovered and executed.")

    await cleanup_db()
    logger.info("🎉 All integration tests passed successfully!")


if __name__ == "__main__":
    asyncio.run(run_integration_tests())
