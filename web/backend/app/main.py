"""ReportLens web API.

    cd web/backend && alembic upgrade head && uvicorn app.main:app --reload --port 8000

The schema is managed by Alembic (migrations/); start-up does not create or change tables.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import inspect

from . import config, verifier_service
from .db import engine
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    if "alembic_version" not in inspect(engine).get_table_names():
        raise RuntimeError("The database has no tables yet. Run `alembic upgrade head` in web/backend first.")
    verifier_service.fail_interrupted()
    yield


app = FastAPI(title="ReportLens", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/api/health")
def health():
    return {"ok": True}
