from agent_framework.schemas.graph_schema import CheckpointerType


class CheckpointerFactory:
    """Creates LangGraph checkpointers by type."""

    @staticmethod
    def create(checkpointer_type: CheckpointerType, graph_name: str):
        match checkpointer_type:
            case CheckpointerType.MEMORY:
                from langgraph.checkpoint.memory import MemorySaver
                return MemorySaver()
            case CheckpointerType.SQLITE:
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
                # In a real setup, we might want to ensure the directory exists
                import os
                os.makedirs(".checkpoints", exist_ok=True)
                db_path = f".checkpoints/{graph_name}.db"
                return AsyncSqliteSaver.from_conn_string(db_path)
