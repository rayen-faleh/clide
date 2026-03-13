.PHONY: lint test check fmt

lint:
	cd backend && uv run ruff check clide/ tests/ && uv run ruff format --check clide/ tests/ && uv run mypy clide/
	cd frontend && npm run lint

test:
	cd backend && uv run pytest tests/ -v --tb=short
	cd frontend && npm run test:run

check: lint test

fmt:
	cd backend && uv run ruff format clide/ tests/ && uv run ruff check --fix clide/ tests/
	cd frontend && npm run format
