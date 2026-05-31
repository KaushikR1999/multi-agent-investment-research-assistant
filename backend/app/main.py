from fastapi import FastAPI

from backend.app.api.health import router as health_router

app = FastAPI(
    title="Multi-Agent Investment Research Assistant",
    version="0.1.0",
    description="Evidence-grounded investment research assistant API.",
)

app.include_router(health_router)
