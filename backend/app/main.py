from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, files, jobs, settings
from app.core.config import settings as app_settings
from app.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Path(app_settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    init_db()
    yield
    # Shutdown (nothing to clean up)


app = FastAPI(
    title="TMClean API",
    description="Translation Memory cleaning and QA tool backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(settings.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
