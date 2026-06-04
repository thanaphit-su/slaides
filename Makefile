.PHONY: up down supabase-up supabase-down supabase-status redis-up migrate seed approve-user delete-user api web test test-api test-web install install-api install-web prod-build prod-up prod-down prod-migrate load-rehearsal

up: supabase-up
	@echo "Supabase and Redis ready."

down:
	docker compose down

supabase-up:
	docker compose up -d

supabase-down:
	docker compose down

supabase-status:
	@docker compose ps
	@printf "\nSupabase API/Auth: http://localhost:54321\nSupabase Studio:   http://localhost:54323\nSupabase Postgres: localhost:54322\nSupabase env:      docker/supabase/.env.slaides\n"

redis-up:
	docker compose up -d redis

install-api:
	cd apps/api && python -m pip install -e ".[dev]"

install-web:
	cd apps/web && npm install

install: install-api install-web

migrate:
	cd apps/api && alembic upgrade head

seed:
	cd apps/api && python -m scripts.seed

approve-user:
	@if [ -z "$(EMAIL)" ]; then echo "Usage: make approve-user EMAIL=user@example.com"; exit 2; fi
	cd apps/api && uv run python -m scripts.approve_user "$(EMAIL)"

# Delete a user end-to-end: their decks (cascades widgets/slides/sections),
# owned sessions (cascades participants/transcript), and the AppUser row.
# Pass SUPABASE=1 to also remove the Supabase Auth user via admin API
# (frees the email for re-registration).
delete-user:
	@if [ -z "$(EMAIL)" ]; then echo "Usage: make delete-user EMAIL=user@example.com [SUPABASE=1]"; exit 2; fi
	cd apps/api && SUPABASE=$(SUPABASE) uv run python -m scripts.delete_user "$(EMAIL)"

api:
	cd apps/api && uvicorn slaides.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

test-api:
	cd apps/api && pytest

test-web:
	cd apps/web && npm test

test: test-api test-web

prod-build:
	docker compose -f docker-compose.prod.yml build

prod-up:
	docker compose -f docker-compose.prod.yml up -d

prod-down:
	docker compose -f docker-compose.prod.yml down

prod-migrate:
	docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

load-rehearsal:
	@if [ -z "$(API_URL)" ] || [ -z "$(CODE)" ]; then echo "Usage: make load-rehearsal API_URL=https://host/api/v1 CODE=SLD-XXXX-XX [AUDIENCE=150] [CONCURRENCY=25] [PLACEMENT_ID=live-poll]"; exit 2; fi
	cd apps/api && uv run python -m scripts.load_rehearsal --api-url "$(API_URL)" --code "$(CODE)" --audience "$(or $(AUDIENCE),150)" --concurrency "$(or $(CONCURRENCY),25)" $(if $(PLACEMENT_ID),--placement-id "$(PLACEMENT_ID)",)
