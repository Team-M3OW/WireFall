.PHONY: install dev lint format test run-api run-logs docker-build docker-up clean

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

lint:
	ruff check api/ inference/ model/scripts/
	ruff format --check api/ inference/ model/scripts/

format:
	ruff check --fix api/ inference/ model/scripts/
	ruff format api/ inference/ model/scripts/

typecheck:
	mypy api/ inference/

test:
	pytest tests/ -v --cov=api --cov=inference

run-api:
	uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload

run-logs:
	uvicorn api.logs_service:app --host 0.0.0.0 --port 8002 --reload

docker-build:
	docker compose -f infrastructure/docker-compose.yml build

docker-up:
	docker compose -f infrastructure/docker-compose.yml up -d

docker-down:
	docker compose -f infrastructure/docker-compose.yml down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache .mypy_cache
