"""Settings from the environment.

web_lite/backend/.env is read first; anything it does not set comes from web/backend/.env, so by default the lite
app talks to the same database (and uses the same verifier settings) as the full web app.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent.parent
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(REPO_ROOT / "web" / "backend" / ".env")        # does not override what is already set


def _path(value: str, base: Path) -> Path:
    p = Path(value)
    return p if p.is_absolute() else base / p


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):                 # some hosts still hand out the old scheme
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgresql://"):]

# Kept apart from web/backend/storage: the lite app has its own report ids.
STORAGE_DIR = _path(os.environ.get("LITE_STORAGE_DIR", "storage"), BACKEND_DIR)
VERIFIER_CONFIG = _path(os.environ.get("VERIFIER_CONFIG", "configs/exp/local_real.yaml"), REPO_ROOT)
VERIFIER_POLICY = os.environ.get("VERIFIER_POLICY", "informed")
VERIFIER_PARSER = os.environ.get("VERIFIER_PARSER", "agent")
CORS_ORIGINS = [o.strip() for o in os.environ.get("LITE_CORS_ORIGINS", "http://localhost:5174").split(",") if o.strip()]
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
MAX_QUEUED_RUNS = int(os.environ.get("LITE_MAX_QUEUED_RUNS", "10"))   # open to everyone: cap the waiting line


def require() -> None:
    if not DATABASE_URL:
        raise RuntimeError("Set DATABASE_URL in web_lite/backend/.env or web/backend/.env (see .env.example)")
