"""Application settings.

Database defaults to a local SQLite file for zero-config local runs.
Point ``ADO_DATABASE_URL`` at PostgreSQL to use it, e.g.::

    ADO_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ado

(requires ``pip install 'psycopg[binary]' 'asyncpg'`` and a running Postgres
instance).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# When loaded from the mono-repo (via .pth), __file__ lives at
#   ROOT/apps/api/ai_dev_api/config.py
# so going up three parents lands on ROOT/apps, and four on ROOT.
_here = Path(__file__).resolve()
_REPO_ROOT = _here.parents[3] if _here.parent.name == "ai_dev_api" else _here.parents[2]
DATA_DIR = _REPO_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADO_", env_file=".env", extra="ignore")

    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'ai_dev.sqlite3'}"
    cors_origins: list[str] = ["http://localhost:3000"]
    speed: float = 1.0  # demo pacing: higher = faster event stream
    host: str = "0.0.0.0"
    port: int = 8000

    # FORGE execution mode: "mock" or "hermes"
    forge_mode: str = "mock"
    forge_timeout: int = 600  # seconds
    forge_workspace_root: Path = _REPO_ROOT / "workspaces"


settings = Settings()