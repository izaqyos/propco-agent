.DEFAULT_GOAL := help
UV ?= uv
RUN := $(UV) run

.PHONY: help sync lint fmt type test cov check e2e-browser eval run docker-build docker-run licenses clean

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

sync: ## install all deps (incl. dev) into .venv
	$(UV) sync --all-extras

lint: ## ruff check + format check
	$(RUN) ruff check .
	$(RUN) ruff format --check .

fmt: ## ruff format + autofix
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

type: ## mypy strict
	$(RUN) mypy

test: ## fast tests (unit/component/api/e2e AppTest), no coverage gate
	$(RUN) pytest -q

cov: ## tests with coverage gate (fail_under from pyproject)
	$(RUN) pytest --cov --cov-report=term-missing --cov-report=xml

check: lint type cov ## everything CI runs

e2e-browser: ## Playwright smoke against a live Streamlit server (fake LLM)
	$(RUN) pytest -m browser --no-cov -q

eval: ## live eval vs local Ollama (skips if unreachable)
	$(RUN) pytest -m live --no-cov -q -s tests/eval

run: ## start the Streamlit UI
	$(RUN) streamlit run app/streamlit_app.py

licenses: ## fail on non-permissive licences in runtime deps (SPDX-aware, dev tools excluded)
	$(RUN) python scripts/check_licenses.py

docker-build: ## build image
	docker build -t propco-agent:local .

docker-run: ## run image on :8501 (expects Ollama on host)
	docker run --rm -p 8501:8501 --env-file .env -e PROPCO_OLLAMA_BASE_URL=http://host.docker.internal:11434 propco-agent:local

clean: ## remove caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov playwright-report test-results
