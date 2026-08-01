from __future__ import annotations

from fastapi import FastAPI

from app.api_routes import router

app = FastAPI(
    title="Incident RCA API",
    version="0.1.0",
    description="Store alerts and run RCA analysis for incident investigations.",
)
app.include_router(router)
