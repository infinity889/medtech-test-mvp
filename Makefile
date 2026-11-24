SHELL := /usr/bin/env bash
.PHONY: net-up db-up db-down backend-build migrate test-ingestion lint typecheck ingest

NETWORK := medprice-net
PG_CONTAINER := medprice-pg
PG_IMAGE := docker.io/library/postgres:16-alpine
BACKEND_IMAGE := medprice-backend:dev

PG_USER := medprice
PG_PASSWORD := medprice
PG_DB := medprice
PG_TEST_DB := medprice_test

DATABASE_URL := postgresql+psycopg://$(PG_USER):$(PG_PASSWORD)@$(PG_CONTAINER):5432/$(PG_DB)
TEST_DATABASE_URL := postgresql+psycopg://$(PG_USER):$(PG_PASSWORD)@$(PG_CONTAINER):5432/$(PG_TEST_DB)

PYTEST_ARGS ?= tests/ingestion
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
		$(BACKEND_IMAGE) pytest $(PYTEST_ARGS) --cov=app.ingestion --cov-report=term-missing

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
