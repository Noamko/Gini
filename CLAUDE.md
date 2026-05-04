# Gini

Full-stack AI assistant platform: multi-agent orchestration, tool execution, messaging integrations.

## Stack
- **Backend**: Python 3.12, FastAPI, SQLAlchemy (async), Alembic, `uv`. Lives in `backend/`.
- **Frontend**: Next.js 15, React 19, Tailwind v4, Zustand, `bun`. Lives in `frontend/`.
- **Infra**: PostgreSQL 16 + pgvector, Redis 7, nginx proxy, sandboxed Docker containers for shell tools. Orchestrated via `docker compose`.

## Common commands
All day-to-day work goes through the Makefile:
- `make dev` — full stack with hot reload (backend + frontend + db + redis + proxy)
- `make migrate` — `alembic upgrade head` inside the backend container
- `make seed` — seed main agent + tools
- `make logs-backend` / `make logs-frontend`
- `make down` / `make clean` (clean drops volumes)

Backend lint + tests (must match CI in `.github/workflows/ci.yml`):
- `cd backend && uv run ruff check app/ tests/`
- `cd backend && uv run ruff format --check app/ tests/`
- `cd backend && uv run pytest tests/ -v`

Frontend:
- `cd frontend && bun run dev` / `build` / `lint`

## Code conventions
- Ruff: target py312, line-length 120, rules `E,F,I,UP,B,SIM,ASYNC` with project-specific ignores already configured in `backend/pyproject.toml` — don't re-add ignored rules without reason.
- Pytest is in `asyncio_mode = "auto"`; tests in `backend/tests/` are async by default.
- First-party import root is `app` (isort knows this).
- DB sessions use SQLAlchemy async; comparisons against booleans on Column expressions (`==True`) are intentional and lint-ignored.

## Architecture pointers
- HTTP/WS entry: `backend/app/main.py` → routers under `backend/app/api/`
- Agent loop / orchestration: `backend/app/services/agent_orchestrator.py`, `chat_execution.py`, `autonomous_execution.py`
- LLM calls: `backend/app/services/llm_gateway.py`
- Tools registry + execution: `backend/app/tools/` (one file per tool) + `services/tool_runner.py` + `services/tool_catalog.py`
- Telegram bot integration: `backend/app/services/telegram_bot.py`
- Sandboxed shell execution: `backend/app/sandbox/` + `sandbox/Dockerfile`
- Frontend app router pages: `frontend/src/app/`; shared state in `frontend/src/stores/`

## Database / migrations
- Alembic migrations in `backend/alembic/versions/`
- Two historical revisions are intentionally no-op stubs to unblock fresh installs: `a1b2c3d4e5f6_create_memories_table.py` and `c9d0e1f2a3b4_remove_memories.py`. Don't "restore" them — they were broken.

## Deployment
This repo deploys to a Raspberry Pi (`gini` Tailscale node, `gini.tail3d4a2.ts.net`). On the Pi the user is not in the `docker` group on login shells, so wrap docker commands as `sg docker -c "..."`. nginx config and TLS certs are wired to that hostname.

## Things to avoid
- Don't bypass ruff/format checks — CI runs them and `--no-verify` on commits is off-limits unless explicitly asked.
- Don't add backwards-compat shims for removed code; delete cleanly.
- Don't mock the database in tests that exercise migrations or persistence behavior.
