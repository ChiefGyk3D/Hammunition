# Local development entry points.
#
# CI is the authority: it pins Python 3.11+ and runs mypy --strict. A dev
# machine on an older interpreter can still run `make test` and `make docs`,
# but `make types` requires 3.11+ and the dev extras.
#
# Nothing here installs into system Python. Use `make venv` first.

PY      ?= python3
VENV    ?= .venv
BIN     := $(VENV)/bin
DOCKER  ?= docker

.PHONY: help venv test types lint docs matrix check containers clean

help:
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | expand -t22

venv: ## Create the dev virtualenv (never touches system Python)
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -e ".[dev]"
	@$(BIN)/python -V

test: ## Run the test suite
	$(BIN)/pytest

types: ## mypy --strict — the gate CLAUDE.md requires
	$(BIN)/mypy --strict

lint: ## ruff check + format check
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

docs: ## Fail on broken internal documentation references
	$(PY) scripts/check_doc_links.py

matrix: ## Print the capability matrix for all declared targets
	$(PY) scripts/capability_matrix.py

check: lint types test docs ## Everything CI runs, minus containers

containers: ## Build and validate every target container (needs a working docker)
	@bash scripts/run-targets.sh

clean:
	rm -rf $(VENV) .pytest_cache .mypy_cache .ruff_cache
	find . -name __pycache__ -prune -exec rm -rf {} +
