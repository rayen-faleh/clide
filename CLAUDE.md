# CLIDE - Development Guide

## Project Structure
- `backend/` — Python FastAPI backend (managed with `uv`)
- `frontend/` — Vue.js 3 + TypeScript frontend (managed with `npm`)
- `config/` — Runtime YAML configuration files

## Commands (always run from project root)
- `make lint` — Run all linters (ruff, mypy, eslint)
- `make test` — Run all tests (pytest, vitest)
- `make check` — Run lint + test (must pass before committing)
- `make fmt` — Auto-format all code

## Backend
- Package manager: `uv`
- Install deps: `uv sync --directory backend`
- Run server: `cd backend && uv run uvicorn clide.main:app --reload`
- Run tests: `cd backend && uv run pytest tests/ -v`
- Python 3.12+, strict mypy, ruff linting

## Frontend
- Package manager: `npm`
- Install deps: `npm install --prefix frontend`
- Dev server: `npm run dev --prefix frontend`
- Run tests: `npm run test:run --prefix frontend`
- Vue 3 + TypeScript + Composition API

## Conventions
- All Python code must pass `ruff check` and `mypy --strict`
- All Vue code must pass `eslint` and `prettier --check`
- WebSocket message types defined in `backend/clide/api/schemas.py` (Pydantic) and `frontend/src/types/messages.ts` (TypeScript) — MUST stay in sync
- Use relative imports within the `clide` package
- Tests required for all new functionality
- TDD: write tests first, then implement
