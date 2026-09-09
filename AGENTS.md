# Repository Guidelines

## Project Structure & Module Organization

HarnessQuest combines a FastAPI backend, React/TypeScript frontend, and Python SDK for agent-session ingestion and case management.

- `backend/app/`: API routes, SQLAlchemy models, schemas, migrations, and integration services. Backend tests live in `backend/tests/`.
- `frontend/src/`: feature modules under `modules/`, shared `components/`, page/layout wiring, API utilities, and `assets/styles.css`.
- `sdk/python/harnessquest_sdk/`: upload client, CLI, and record converters.
- `examples/`: sample session payloads. `docs/`: architecture, OAuth, and search documentation.
- `docker-compose.yml`: API, worker, web, PostgreSQL, Redis, MinIO, and Langfuse services.

## Build, Test, and Development Commands

Run commands from the repository root unless indicated.

- `pip install -r backend/requirements.txt` and `pip install -e sdk/python`: install backend tooling and the editable SDK in a virtual environment.
- `cd frontend && npm install`: install frontend dependencies; `npm run dev` starts Vite from that directory.
- `cp .env.example .env`: initialize local configuration when `.env` is absent.
- `docker compose up -d --build`: build and start the complete stack.
- `make build`: build API and web images.
- `make lint`: run Ruff, mypy, and ESLint. `make format`: format and autofix Python source.
- `make check`: compile/check Python, typecheck/lint/build the frontend, and validate Compose configuration. Run tests separately.
- `PYTHONPATH=backend python -m pytest backend/tests`: run backend tests.

## Coding Style & Naming Conventions

Use four-space Python indentation, double quotes, type annotations, and Ruff’s 120-character line limit. Use `snake_case` for functions/modules and `PascalCase` for classes.

Follow existing TypeScript style: two-space indentation, single quotes, semicolons, `PascalCase` components, and `camelCase` functions. Prefer `type` aliases as required by ESLint; TypeScript strict mode is enabled.

## Testing Guidelines

Use pytest and FastAPI TestClient with shared fixtures in `backend/tests/conftest.py`. Name files `test_*.py` and functions `test_<behavior>`. Default database tests use temporary SQLite. PostgreSQL search checks require `HQ_SEARCH_TEST_DATABASE_URL` pointing to a test database. Add regression tests for changed behavior; no numeric coverage threshold or frontend test runner is configured.

## Commit & Pull Request Guidelines

Follow history’s `feat: ...` and `fix: ...` prefixes; include issue references when applicable, such as `(#TOL-95)`. PRs should describe behavior changes, link relevant issues, report validation, and include screenshots for UI changes. Document configuration or migration effects.

## Security & Configuration

Keep secrets in ignored `.env` files. Replace default credentials before shared deployment; never commit tokens or certificate private keys.
