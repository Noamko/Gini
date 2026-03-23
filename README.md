# Gini

A full-stack AI assistant platform with multi-agent orchestration, tool execution, and messaging integrations.

## Features

- **Multi-Agent System** — Create specialized agents with custom prompts, skills, and credentials. Agents can delegate tasks to each other.
- **Chat Interface** — Real-time WebSocket chat with streaming responses, tool call visualization, and human-in-the-loop approval.
- **Background Runs** — Execute agents in the background with live status tracking (pending/running/done/failed).
- **Skills & Credentials** — Assign reusable skills and encrypted credentials to agents. Trusted agents get credentials injected automatically.
- **Tool Execution** — Built-in tools: shell commands, file I/O, HTTP requests, Telegram messaging, task delegation. Sandboxed execution with configurable network access.
- **Memory / RAG** — Semantic search over agent memories using pgvector embeddings (OpenAI text-embedding-3-small).
- **Execution Traces** — Full observability into agent reasoning: LLM calls, tool executions, delegations, with cost and timing.
- **Telegram Bot** — Chat with Gini from Telegram. Switch agents, run background tasks, get notified on completion.
- **Messaging Agents** — WhatsApp and Telegram messaging via dedicated agents.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic |
| Frontend | Next.js 15, React 19, Tailwind CSS, Zustand |
| Database | PostgreSQL 16 + pgvector |
| Cache | Redis 7 |
| LLM | Anthropic (Claude), OpenAI |
| Infra | Docker Compose, sandboxed containers |
| Package Managers | uv (Python), bun (Node) |

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env  # Add your API keys

# 2. Start everything
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 3. Run database migrations
docker compose exec gini-backend uv run alembic upgrade head

# 4. Seed initial data
docker compose exec gini-backend uv run python -m scripts.seed_tools
docker compose exec gini-backend uv run python -m scripts.seed_main_agent

# 5. Open the UI
open http://localhost:3000
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude models |
| `OPENAI_API_KEY` | OpenAI API key for embeddings and models |
| `ENCRYPTION_KEY` | Fernet key for credential encryption |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (optional, from @BotFather) |

## Architecture

```
Browser/Telegram
      |
  [Next.js Frontend :3000]  ←→  [FastAPI Backend :8000]
                                      |
                            ┌─────────┼─────────┐
                            |         |         |
                       [PostgreSQL] [Redis]  [Sandbox]
                        + pgvector   cache   containers
```

- **Frontend** connects to backend via REST API and WebSocket
- **Backend** orchestrates agents, manages tools, and handles LLM calls
- **Sandbox** containers execute shell commands with configurable network isolation
- **Redis** caches prompts, model lists, and handles pub/sub for real-time updates

## License

MIT
