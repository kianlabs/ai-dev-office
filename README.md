# AI Dev Office

Multi-agent developer workspace — an "AI developer control room" Web dashboard.

The user submits one development task ("Add authentication to Next.js project").
ATLAS (Engineering Manager) plans subtasks, dispatches SCOUT (research), FORGE
(coding), QA (testing), PULSE (monitoring), reviews the outcome, and reports a
summary — all streamed live to the UI over WebSocket.

> The MVP ships with **mock executors only**. No LLM is called and **no
> autonomous shell execution** is performed. The `AgentExecutor` interface is
> designed so a real runtime (Hermes, OpenAI, Claude, a local LLM) can be
> mounted later without touching the dashboard or orchestration.

---

## Stack

| Layer    | Tech                                             |
| -------- | ------------------------------------------------ |
| Frontend | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS |
| Backend  | FastAPI (Python 3.11+), SQLAlchemy 2 (async)     |
| Database | PostgreSQL (via SQLAlchemy), SQLite by default for zero-config local run |
| Realtime | WebSocket (single `/ws` stream)                  |
| Agents   | Agent registry · task queue · event system · tool abstraction |

---

## Monorepo layout

```
ai-dev-office/
├─ apps/
│  ├─ web/                     # Next.js control-room dashboard
│  │  └─ app/, components/, lib/
│  └─ api/                     # FastAPI backend (ai_dev_api)
│     └─ ai_dev_api/
│        ├─ main.py            # app bootstrap, wiring
│        ├─ config.py          # settings (ADO_* env)
│        ├─ db.py / models.py  # async SQLAlchemy persistence
│        ├─ realtime.py        # websocket bus
│        ├─ routes.py          # /api/* REST + /ws
│        ├─ app_state.py       # module-level live state
│        └─ agents.py          # binds 5 mock agents into the registry
├─ agents/
│  ├─ atlas/  →  ai_dev_agent_atlas   # Engineering Manager / orchestrator
│  ├─ scout/  →  ai_dev_agent_scout   # Research
│  ├─ forge/  →  ai_dev_agent_forge   # Coding
│  ├─ qa/     →  ai_dev_agent_qa      # Testing
│  └─ pulse/  →  ai_dev_agent_pulse   # Monitoring
├─ packages/
│  ├─ agent-core/ → ai_dev_agent_core # AgentExecutor contract, registry, orchestration engine
│  ├─ shared/     → ai_dev_shared     # domain enums + pydantic models + agent catalog
│  └─ tools/      → ai_dev_tools      # tool abstraction + deterministic mock tools
├─ requirements.txt
└─ docker-compose.yml            # optional PostgreSQL
```

### Key design points

- **`AgentExecutor` contract** (`packages/agent-core/.../executor.py`):
  `execute(task, ctx) -> AsyncIterator[AgentEvent]`. Everything the app knows
  about an agent flows through events — swap in `HermesExecutor`, `OpenAIExecutor`,
  etc. by registering a new factory in `apps/api/ai_dev_api/agents.py`.
- **Orchestration engine** (`agent-core/.../engine.py`): drives a task through
  the orchestrator executor, echoes agent status onto the registry, mirrors
  task state, appends to the activity feed, and broadcasts over the bus. Single
  orchestrator slot → extra tasks stay `QUEUED`.
- **Event system**: `STATUS / LOG / SUBTASKS / QA_RESULT / HEALTH / REVIEW / RESULT`.
- **Tools**: `ToolChest` abstraction with deterministic stubs
  (`read_docs`, `read_project_tree`, `write_code`, `run_check`, `poll_deployment`).
  Real shells/filesystem are deliberately NOT bound in the MVP.
- **Mock executors** fake believable progress so the whole control-room flow is
  testable end-to-end without any LLM.

---

## Running the project

### 1. Backend (API)

```bash
cd ai-dev-office

# Create a virtualenv and install third-party deps
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Expose the local packages to the interpreter.
# The default location for this setup is already present as
# .venv/lib/python3.14/site-packages/ai_dev_office.pth
# For a fresh machine, recreate it with absolute source paths:
#   cat > .venv/lib/python3.*/site-packages/ai_dev_office.pth <<'EOF'
#   /abs/path/ai-dev-office/packages/shared
#   /abs/path/ai-dev-office/packages/agent-core
#   /abs/path/ai-dev-office/packages/tools
#   /abs/path/ai-dev-office/agents/scout
#   /abs/path/ai-dev-office/agents/forge
#   /abs/path/ai-dev-office/agents/qa
#   /abs/path/ai-dev-office/agents/pulse
#   /abs/path/ai-dev-office/agents/atlas
#   /abs/path/ai-dev-office/apps/api
#   EOF

# Run the API (SQLite by default, no Postgres needed)
ADO_SPEED=1.0 .venv/bin/uvicorn ai_dev_api.main:app --port 8000
```

Demo pacing: raise `ADO_SPEED` (e.g. `8.0`) to make the agents stream events
faster.

**Optional PostgreSQL:**

```bash
docker compose up -d db
pip install asyncpg
ADO_DATABASE_URL=postgresql+asyncpg://ado:ado@localhost:5432/ai_dev_office \
  .venv/bin/uvicorn ai_dev_api.main:app --port 8000
```

### 2. Frontend (Web)

In a second terminal:

```bash
cd ai-dev-office/apps/web
npm install
npm run dev          # http://localhost:3000
```

The dashboard talks to the API via a Next.js rewrite (`/api/*` → `:8000`) for
REST and connects to the `:8000/ws` WebSocket directly.

- For **production** connect mode set the env vars before building/starting:
  `NEXT_PUBLIC_WS_HOST=localhost:8000 npm run build && npm run start`
- The in-repo `apps/web/.env.example` documents both overrides.

Open **http://localhost:3000**, type any development task, and press
**Dispatch to ATLAS**. Watch the 5 agent cards and the live activity feed.

---

## Control-room features (MVP)

- Title bar with live connected/system status + agent glyphs
- Stat cards: Tasks · Running · Completed · Failed
- **Agent Bay**: 5 agent cards (ATLAS · SCOUT · FORGE · QA · PULSE) with
  role, live status dot, and current activity line
- Create-task form with quick suggestions
- Task list with status chips and per-agent subtask breakdown
- Right-hand **Activity Feed** with timestamps (`10:34 ATLAS created 3 subtasks` …)

### Status model

| Task   | QUEUED · PLANNING · RUNNING · REVIEW · DONE · FAILED |
| ------ | ---------------------------------------------------- |
| Agent  | IDLE · WORKING · WAITING · ERROR                     |

---

## API surface

| Method | Path              | Description                        |
| ------ | ----------------- | ---------------------------------- |
| GET    | `/`               | service info                       |
| GET    | `/api/health`     | liveness                           |
| GET    | `/api/snapshot`   | tasks + agents + activity + stats  |
| GET    | `/api/tasks`      | list tasks                         |
| POST   | `/api/tasks`      | create + enqueue a task            |
| DELETE | `/api/tasks/{id}` | cancel a queued task               |
| GET    | `/api/agents`     | agent statuses                     |
| GET    | `/api/activity`   | recent feed entries                |
| WS     | `/ws`             | realtime: snapshot, feed, agent/task updates |

To make a task fail for demo purposes, include `fail` in its title/description
(the mock QA gate mirrors this deterministically).

---

## Verification

- `npm run typecheck` — TypeScript clean
- `npm run lint` — ESLint clean
- `npm run build` — Next.js production build passes
- Backend end-to-end pipeline (single task → DONE) and two-task queue (first
  FAIL, second DONE) verified using the real uvicorn server + websocket client
  during development.
