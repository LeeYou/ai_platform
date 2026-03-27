"""FastAPI application entrypoint for the Training Management backend."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import Base, engine
from routers import capabilities, datasets, jobs, models, ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("./data/logs", exist_ok=True)
    os.makedirs("./data/models", exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Train Management API",
    version="1.0.0",
    description="Backend for AI model training, monitoring and model package export",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(capabilities.router)
app.include_router(datasets.router)
app.include_router(jobs.router)
app.include_router(models.router)
app.include_router(ws.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
