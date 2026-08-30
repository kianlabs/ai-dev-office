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
    # Phase 1: Enable real Hermes execution by default
    forge_mode: str = "hermes"
    forge_timeout: int = 600  # seconds
    forge_workspace_root: Path = _REPO_ROOT / "workspaces"

    # FORGE / Hermes model resolution. FORGE must NOT hardcode a model or
    # provider; it defers to the active Hermes configuration (config.yaml)
    # unless an explicit override is provided here. Both are optional.
    # Leave empty to use Hermes' configured default model/provider.
    forge_model: str = ""          # e.g. "kr/claude-sonnet-4.5" (override only)
    forge_provider: str = ""       # e.g. "custom:archkian" (override only)
    forge_max_turns: int = 12      # bounded Hermes loop guard (override via env)

    # SCOUT execution mode: "mock" or "real"
    # Phase 3: Enable real read-only repository research by default.
    # "mock" emits canned demo narrative without touching the filesystem.
    scout_mode: str = "real"

    # QA execution mode: "mock" or "deterministic"
    # Phase 2: Enable REAL deterministic QA (runs detected project checks
    # in a read-only sandbox) by default. "mock" emits canned demo results.
    qa_mode: str = "deterministic"
    qa_timeout: int = 180

    # PULSE execution mode: "mock" or "deterministic"
    pulse_mode: str = "mock"


settings = Settings()