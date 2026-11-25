SHELL := /usr/bin/env bash
.PHONY: net-up db-up db-down backend-build migrate test-ingestion test-normalization test-api test-all lint typecheck ingest seed-catalog normalize api-up api-down api-dev web-build web-up web-down test-web lint-web typecheck-web build-web

NETWORK := medprice-net
PG_CONTAINER := medprice-pg
API_CONTAINER := medprice-api
WEB_CONTAINER := medprice-web
PG_IMAGE := docker.io/library/postgres:16-alpine
BACKEND_IMAGE := medprice-backend:dev
WEB_IMAGE := medprice-web:dev

PG_USER := medprice
PG_PASSWORD := medprice
PG_DB := medprice
PG_TEST_DB := medprice_test

DATABASE_URL := postgresql+psycopg://$(PG_USER):$(PG_PASSWORD)@$(PG_CONTAINER):5432/$(PG_DB)
TEST_DATABASE_URL := postgresql+psycopg://$(PG_USER):$(PG_PASSWORD)@$(PG_CONTAINER):5432/$(PG_TEST_DB)

PYTEST_ARGS ?= tests/ingestion
NORM_PYTEST_ARGS ?= tests/normalization
API_PYTEST_ARGS ?= tests/api
SOURCE ?= all
EXTRA_ARGS ?=

net-up:
	@podman network exists $(NETWORK) || podman network create $(NETWORK)

db-up: net-up
	@if podman container exists $(PG_CONTAINER); then \
		podman start $(PG_CONTAINER) >/dev/null; \
	else \
		podman run -d --name $(PG_CONTAINER) --network $(NETWORK) \
			-e POSTGRES_USER=$(PG_USER) \
			-e POSTGRES_PASSWORD=$(PG_PASSWORD) \
			-e POSTGRES_DB=$(PG_DB) \
			-p 5432:5432 $(PG_IMAGE) >/dev/null; \
	fi
	@for i in $$(seq 1 30); do \
		if podman exec $(PG_CONTAINER) pg_isready -U $(PG_USER) -d $(PG_DB) >/dev/null 2>&1; then \
			break; \
		fi; \
		sleep 1; \
	done
	@podman exec $(PG_CONTAINER) pg_isready -U $(PG_USER) -d $(PG_DB)
	@podman exec $(PG_CONTAINER) psql -U $(PG_USER) -d $(PG_DB) -tc \
		"SELECT 1 FROM pg_database WHERE datname = '$(PG_TEST_DB)'" | grep -q 1 \
		|| podman exec $(PG_CONTAINER) psql -U $(PG_USER) -d $(PG_DB) -c "CREATE DATABASE $(PG_TEST_DB);"

db-down:
	@podman rm -f $(PG_CONTAINER) >/dev/null 2>&1 || true

backend-build:
	podman build -t $(BACKEND_IMAGE) -f backend/Containerfile backend

migrate: db-up
	podman run --rm --network $(NETWORK) -v $(CURDIR)/backend:/app:Z \
		-e DATABASE_URL=$(DATABASE_URL) \
		$(BACKEND_IMAGE) alembic upgrade head

test-ingestion: db-up
	podman run --rm --network $(NETWORK) -v $(CURDIR)/backend:/app:Z \
		-e DATABASE_URL=$(TEST_DATABASE_URL) \
		$(BACKEND_IMAGE) sh -c "alembic upgrade head && pytest $(PYTEST_ARGS) --cov=app.ingestion --cov-report=term-missing"

test-normalization: db-up
	podman run --rm --network $(NETWORK) -v $(CURDIR)/backend:/app:Z \
		-e DATABASE_URL=$(TEST_DATABASE_URL) \
		$(BACKEND_IMAGE) sh -c "alembic upgrade head && pytest $(NORM_PYTEST_ARGS) --cov=app.normalization --cov-report=term-missing"

test-api: db-up
	podman run --rm --network $(NETWORK) -v $(CURDIR)/backend:/app:Z \
		-e DATABASE_URL=$(TEST_DATABASE_URL) \
		$(BACKEND_IMAGE) sh -c "alembic upgrade head && pytest $(API_PYTEST_ARGS) --cov=app.api --cov=app.main --cov-report=term-missing"

test-all: db-up
	podman run --rm --network $(NETWORK) -v $(CURDIR)/backend:/app:Z \
		-e DATABASE_URL=$(TEST_DATABASE_URL) \
		$(BACKEND_IMAGE) sh -c "alembic upgrade head && pytest tests --cov=app --cov-report=term-missing"

lint:
	podman run --rm -v $(CURDIR)/backend:/app:Z \
		$(BACKEND_IMAGE) ruff check app tests

typecheck:
	podman run --rm -v $(CURDIR)/backend:/app:Z \
		$(BACKEND_IMAGE) mypy app

ingest: db-up
	podman run --rm --network $(NETWORK) -v $(CURDIR)/backend:/app:Z \
		-e DATABASE_URL=$(DATABASE_URL) \
		$(BACKEND_IMAGE) python -m app.ingestion.cli run --source $(SOURCE) $(EXTRA_ARGS)

seed-catalog: db-up
	podman run --rm --network $(NETWORK) -v $(CURDIR)/backend:/app:Z \
		-e DATABASE_URL=$(DATABASE_URL) \
		$(BACKEND_IMAGE) python -m app.normalization.cli seed-catalog

normalize: db-up
	podman run --rm --network $(NETWORK) -v $(CURDIR)/backend:/app:Z \
		-e DATABASE_URL=$(DATABASE_URL) \
		$(BACKEND_IMAGE) python -m app.normalization.cli run $(EXTRA_ARGS)

api-up: db-up
	@podman rm -f $(API_CONTAINER) >/dev/null 2>&1 || true
	podman run -d --name $(API_CONTAINER) --network $(NETWORK) \
		-v $(CURDIR)/backend:/app:Z \
		-e DATABASE_URL=$(DATABASE_URL) \
		-p 8000:8000 $(BACKEND_IMAGE) \
		uvicorn app.main:app --host 0.0.0.0 --port 8000

api-down:
	@podman rm -f $(API_CONTAINER) >/dev/null 2>&1 || true

api-dev: db-up
	podman run --rm -it --network $(NETWORK) -v $(CURDIR)/backend:/app:Z \
		-e DATABASE_URL=$(DATABASE_URL) \
		-p 8000:8000 $(BACKEND_IMAGE) \
		uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

web-build:
	podman build -t $(WEB_IMAGE) -f frontend/Containerfile frontend

web-up: net-up
	@podman rm -f $(WEB_CONTAINER) >/dev/null 2>&1 || true
	podman run -d --name $(WEB_CONTAINER) --network $(NETWORK) \
		-v $(CURDIR)/frontend:/workspace/app:Z \
		-e VITE_API_PROXY_TARGET=http://$(API_CONTAINER):8000 \
		-p 5173:5173 $(WEB_IMAGE) \
		vite --host 0.0.0.0 --port 5173

web-down:
	@podman rm -f $(WEB_CONTAINER) >/dev/null 2>&1 || true

test-web:
	podman run --rm -v $(CURDIR)/frontend:/workspace/app:Z \
		$(WEB_IMAGE) vitest run

lint-web:
	podman run --rm -v $(CURDIR)/frontend:/workspace/app:Z \
		$(WEB_IMAGE) eslint src

typecheck-web:
	podman run --rm -v $(CURDIR)/frontend:/workspace/app:Z \
		$(WEB_IMAGE) tsc --noEmit

build-web:
	podman run --rm -v $(CURDIR)/frontend:/workspace/app:Z \
		$(WEB_IMAGE) vite build
