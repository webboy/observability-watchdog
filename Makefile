.DEFAULT_GOAL := help

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
ALEMBIC := $(VENV)/bin/alembic
UVICORN := $(VENV)/bin/uvicorn
PYTEST := $(VENV)/bin/pytest
STREAMLIT := $(VENV)/bin/streamlit
COMPOSE := docker compose

API_HOST ?= 0.0.0.0
API_PORT ?= 8000
DASHBOARD_PORT ?= 8501

POSTGRES_USER ?= watchdog
POSTGRES_DB ?= watchdog

.PHONY: help install db db-down db-clear-data migrate api dashboard test up down logs

help: ## Show available targets
	@echo "Observability Watchdog — development targets"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: $(VENV)/.installed ## Create virtualenv and install Python dependencies

$(VENV)/.installed: requirements.txt
	@test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt
	@touch $(VENV)/.installed

db: ## Start local PostgreSQL via Docker Compose
	$(COMPOSE) up -d db

db-down: ## Stop local PostgreSQL container
	$(COMPOSE) stop db

db-clear-data: db ## Truncate dynamic tables; keep apps and anomaly rules
	$(COMPOSE) exec -T db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c \
		"TRUNCATE TABLE alerts, anomalies, ingestion_runs, metric_windows, log_events RESTART IDENTITY CASCADE;"

migrate: install db ## Run Alembic migrations against the local database
	$(ALEMBIC) upgrade head

api: install ## Run FastAPI locally with auto-reload
	$(UVICORN) app.main:app --reload --host $(API_HOST) --port $(API_PORT)

dashboard: install ## Run Streamlit dashboard locally
	@test -f dashboard/streamlit_app.py || (echo "Error: dashboard/streamlit_app.py not found (Phase 5)." && exit 1)
	@test -x $(STREAMLIT) || (echo "Error: streamlit is not installed. Add it to requirements.txt and run 'make install'." && exit 1)
	PYTHONPATH=. $(STREAMLIT) run dashboard/streamlit_app.py --server.port $(DASHBOARD_PORT)

test: install ## Run pytest test suite
	$(PYTEST) -v

up: ## Build and start the full Docker Compose stack (db + api)
	$(COMPOSE) up --build

down: ## Stop and remove Docker Compose containers
	$(COMPOSE) down

logs: ## Follow Docker Compose logs
	$(COMPOSE) logs -f
