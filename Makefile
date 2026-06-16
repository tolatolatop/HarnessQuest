.PHONY: lint lint-python lint-frontend format format-python check check-python check-frontend build

lint: lint-python lint-frontend

lint-python:
	python -m ruff check backend/app sdk/python/harnessquest_sdk
	python -m mypy backend/app sdk/python/harnessquest_sdk

lint-frontend:
	cd frontend && npm run lint

format: format-python

format-python:
	python -m ruff format backend/app sdk/python/harnessquest_sdk
	python -m ruff check --fix backend/app sdk/python/harnessquest_sdk

check: check-python check-frontend
	docker compose config >/tmp/harnessquest-compose.yml

check-python:
	python -m compileall backend/app sdk/python/harnessquest_sdk
	python -m ruff check backend/app sdk/python/harnessquest_sdk
	python -m mypy backend/app sdk/python/harnessquest_sdk

check-frontend:
	cd frontend && npm run typecheck && npm run lint && npm run build

build:
	docker compose build api web

