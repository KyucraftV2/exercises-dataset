.DEFAULT_GOAL := help

VENV_DIR := .venv
PYTHON   := $(VENV_DIR)/bin/python
PIP      := $(VENV_DIR)/bin/pip
UVICORN  := $(VENV_DIR)/bin/uvicorn
PYTEST   := $(VENV_DIR)/bin/pytest
RUFF     := $(VENV_DIR)/bin/ruff

HOST ?= 127.0.0.1
PORT ?= 8000

.PHONY: help venv install install-dev env run start test lint format check clean distclean reset-db

help: ## Affiche cette aide
	@echo "Cibles disponibles :"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

$(VENV_DIR)/bin/activate:
	python3 -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip

venv: $(VENV_DIR)/bin/activate ## Crée le virtualenv (.venv)

install: venv ## Installe les dépendances runtime
	$(PIP) install -r backend/requirements.txt

install-dev: venv ## Installe les dépendances de dev (tests + ruff)
	$(PIP) install -r backend/requirements-dev.txt

.env:
	cp .env.example .env
	@echo "-> .env créé depuis .env.example (AI_MODE=local par défaut)"

env: .env ## Crée le fichier .env s'il n'existe pas encore

run: install env ## Démarre le site (http://$(HOST):$(PORT)) avec rechargement auto
	$(UVICORN) backend.main:app --reload --host $(HOST) --port $(PORT)

start: run ## Alias de "run"

test: install-dev ## Lance la suite de tests (mode AI_MODE=local forcé)
	$(PYTEST) backend/tests/

lint: install-dev ## Vérifie le style avec ruff
	$(RUFF) check .

format: install-dev ## Formate le code avec ruff
	$(RUFF) format .

check: lint test ## Lint + tests, à lancer avant un commit/merge

reset-db: ## Supprime la base SQLite locale (recréée au prochain démarrage)
	rm -f backend/app.db backend/app.db-journal backend/app.db-wal backend/app.db-shm

clean: ## Supprime les caches Python/pytest/ruff
	find . -type d -name '__pycache__' -not -path './.venv/*' -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache

distclean: clean ## clean + supprime le virtualenv
	rm -rf $(VENV_DIR)
