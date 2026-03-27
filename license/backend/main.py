"""FastAPI application entrypoint for the License Management backend."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import Base, engine
from routers import customers, keys, licenses


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure data directories exist
    os.makedirs("./data/licenses", exist_ok=True)
    # Create all DB tables
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="License Management API",
    version="1.0.0",
    description="Backend for issuing, renewing, and revoking AI platform licenses",
    lifespan=lifespan,
)

# CORS — open for all origins in dev mode
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(customers.router)
app.include_router(licenses.router)
app.include_router(keys.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


# Serve built frontend if it exists
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
