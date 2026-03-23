.PHONY: dev up down logs migrate seed build clean

# Development with hot reload
dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Production
up:
	docker compose up --build -d

down:
	docker compose down

# Logs
logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f gini-backend

logs-frontend:
	docker compose logs -f gini-frontend

# Database
migrate:
	docker compose exec gini-backend uv run alembic upgrade head

seed:
	docker compose exec gini-backend uv run python -m scripts.seed_main_agent
	docker compose exec gini-backend uv run python -m scripts.seed_tools

# Build
build:
	docker compose build

# Clean everything including volumes
clean:
	docker compose down -v --remove-orphans
