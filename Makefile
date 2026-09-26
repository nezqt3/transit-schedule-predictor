.PHONY: up down build logs test docs features train submit run-online \
	fe-install fe-dev fe-build fe-check fe-preview fe-clean \
	up-frontend up-frontend-dev

up:
	docker compose up -d

build:
	docker compose build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd backend && python -m pytest
	cd ml && python -m pytest

features:
	cd ml && python -m src.offline.dataset_builder --split all

train:
	cd ml && python -m src.offline.train

submit:
	cd ml && python -m src.offline.predict_submission

run-online:
	docker compose up --build ml backend

lint:
	cd backend && ruff check .

format:
	cd backend && ruff format .

preprocessing:
	cd scripts && python -m scripts.prepare_dataset

docs:
	cd backend && sphinx-build -W --keep-going -b html docs docs/_build/html


# --- frontend: локально (pnpm) ---

fe-install:
	cd frontend && pnpm install --frozen-lockfile

fe-dev:
	cd frontend && pnpm dev

fe-build:
	cd frontend && pnpm build

fe-check:
	cd frontend && pnpm typecheck

fe-preview:
	cd frontend && pnpm preview --port 4173

fe-clean:
	rm -rf frontend/dist frontend/node_modules/.vite

# --- frontend: в docker ---

up-frontend:
	docker compose up -d --build frontend

up-frontend-dev:
	docker compose --profile dev up -d --build frontend-dev

logs-frontend:
	docker compose logs -f frontend
