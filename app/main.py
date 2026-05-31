from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.logging_config import configure_logging
from app.routes.webhook import router as webhook_router
from app.services.database import init_db, close_pool


configure_logging("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown of the shared Postgres connection pool."""
    await init_db()
    yield
    await close_pool()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(webhook_router)
