# Amelia development helpers
# Postgres runs on host port 5434 (see docker-compose.yml)

DB_PORT := $(or $(AMELIA_DB_PORT),5434)
DATABASE_URL := postgresql://amelia:amelia@localhost:$(DB_PORT)/amelia_test

.PHONY: db db-stop test test-unit test-integration test-all lint type-check check dev

## Database
db:                    ## Start postgres (detached)
	docker compose up -d postgres

db-stop:               ## Stop postgres
	docker compose down

## Tests
test:                  ## Run unit tests (no DB required)
	uv run pytest

test-db:               ## Run DB-dependent unit tests
	DATABASE_URL=$(DATABASE_URL) uv run pytest tests/unit/server/

test-integration:      ## Run integration tests (needs DB)
	DATABASE_URL=$(DATABASE_URL) uv run pytest -m integration -o "addopts="

test-all:              ## Run all tests including integration
	DATABASE_URL=$(DATABASE_URL) uv run pytest -o "addopts="

## Quality
lint:                  ## Lint and auto-fix
	uv run ruff check --fix amelia tests

type-check:            ## Type check
	uv run mypy amelia

check:                 ## Run all checks (lint + types + unit tests)
	$(MAKE) lint type-check test

## Dev
dev:                   ## Start full stack (API + dashboard)
	uv run amelia dev

help:                  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
