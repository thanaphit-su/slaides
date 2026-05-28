.PHONY: up down supabase-up supabase-down supabase-status redis-up migrate seed approve-user delete-user api web test test-api test-web install install-api install-web eval-widgets

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

eval-widgets:
	cd apps/api && uv run python -m scripts.eval_widgets $(ARGS)
