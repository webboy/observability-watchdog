"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.apps import router as apps_router
from app.api.health import router as health_router
from app.api.logs import router as logs_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="API-first Intelligent Observability & Event Watchdog",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(apps_router)
app.include_router(logs_router)
