# Lean In Circle recommender: setup, run and verification targets.
# Every target calls the virtual environment's Python directly, so there is nothing to activate.
# Targets that need dependencies install them first if requirements.txt has changed.

.DEFAULT_GOAL := help

PYTHON ?= python3
VENV   := .venv
PY     := $(VENV)/bin/python
STAMP  := $(VENV)/.installed
PORT   ?= 8000

.PHONY: help setup seed run test clean

help: ## List the available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  make %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

$(STAMP): requirements.txt
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11 or newer is required, found " + sys.version.split()[0])'
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --quiet --disable-pip-version-check -r requirements.txt
	@touch $(STAMP)

setup: $(STAMP) ## Create .venv and install the pinned dependencies (Python 3.11+)

seed: $(STAMP) ## Rebuild circles.db from data/
	$(PY) -m app.seed

run: $(STAMP) ## Start the API on port 8000 (or PORT=...), with docs at /docs
	$(PY) -m uvicorn app.main:app --host 127.0.0.1 --port $(PORT)

test: $(STAMP) ## Run the whole test suite
	$(PY) -m pytest

clean: ## Remove .venv, circles.db, reports and caches
	rm -rf $(VENV) circles.db reports .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
