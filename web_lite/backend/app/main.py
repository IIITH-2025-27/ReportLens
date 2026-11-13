"""ReportLens Lite API: open to everyone, no accounts.

    cd web_lite/backend && alembic upgrade head && uvicorn app.main:app --reload --port 8001

The schema is managed by Alembic (migrations/, version table alembic_version_v2); start-up does not create tables.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from . import config, verifier_service
from .db import VERSION_TABLE, engine
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    if VERSION_TABLE not in inspect(engine).get_table_names():
        raise RuntimeError("The lite tables do not exist yet. Run `alembic upgrade head` in web_lite/backend first.")
    verifier_service.fail_interrupted()
    yield


app = FastAPI(title="ReportLens Lite", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/api/health")
def health():
    return {"ok": True}
