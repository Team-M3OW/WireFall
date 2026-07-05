# WireFall — Agent Context

## Commands
- Run API: `uvicorn api.main:app --reload`
- Run Logs service: `uvicorn api.logs_service:app --reload --port 8002`
- Lint: `ruff check api/ inference/`
- Format: `ruff format api/ inference/`
- Typecheck: `mypy api/ inference/ --ignore-missing-imports`
- Test: `pytest tests/ -v`
- Docker: `docker compose -f infrastructure/docker-compose.yml up -d`

## Structure
- `api/` — FastAPI application (routes, services, models)
- `inference/` — ML inference pipeline (model, features, ensemble, rule gen)
- `model/` — Training scripts and artifacts
- `dashboard/` — Static HTML + React dashboards
- `infrastructure/` — Docker, k8s, nginx configs
- `lua/` — OpenResty WAF scripts
- `docs/` — Documentation

## Conventions
- Type hints everywhere
- Config via pydantic-settings/.env
- No comments in code unless complex
- Imports: stdlib → third-party → local
