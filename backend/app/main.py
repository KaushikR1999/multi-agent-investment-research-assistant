import logging

from fastapi import FastAPI

from backend.app.api.health import router as health_router
from backend.app.api.research import router as research_router
from backend.app.config import get_settings

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(
    title="Multi-Agent Investment Research Assistant",
    version="0.1.0",
    description="Evidence-grounded investment research assistant API.",
)

app.include_router(health_router)
app.include_router(research_router)
