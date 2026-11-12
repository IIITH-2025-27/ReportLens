"""Settings from the environment (web/backend/.env)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _path(value: str, base: Path) -> Path:
    p = Path(value)
    return p if p.is_absolute() else base / p


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):                 # some hosts still hand out the old scheme
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgresql://"):]

JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_HOURS = int(os.environ.get("JWT_HOURS", "12"))
STORAGE_DIR = _path(os.environ.get("STORAGE_DIR", "storage"), BACKEND_DIR)
VERIFIER_CONFIG = _path(os.environ.get("VERIFIER_CONFIG", "configs/exp/local_real.yaml"), REPO_ROOT)
VERIFIER_POLICY = os.environ.get("VERIFIER_POLICY", "informed")
VERIFIER_PARSER = os.environ.get("VERIFIER_PARSER", "agent")
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))


def require() -> None:
    missing = [n for n, v in (("DATABASE_URL", DATABASE_URL), ("JWT_SECRET", JWT_SECRET)) if not v]
    if missing:
        raise RuntimeError(f"Set {', '.join(missing)} in web/backend/.env (see .env.example)")
