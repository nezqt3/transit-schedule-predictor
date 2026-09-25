.PHONY: up down build logs test docs

up:
	docker compose up -d

build:
	docker compose build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd backend && pytest

lint:
	cd backend && ruff check .

format:
	cd backend && ruff format .

docs:
	cd backend && sphinx-build -b html docs docs/_build/html