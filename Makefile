.PHONY: up down build logs test features train submit run-online up-ndtp \
	up-dataset-replay replay-start logs-dataset-replay lint format preprocessing docs \
	fe-install fe-dev fe-build fe-check fe-preview fe-clean \
	up-frontend up-frontend-dev logs-frontend

NDTP_EMULATOR_ARCHIVE ?= emulator/ndtp-telemetry-emulator.tar

up:
	python scripts/start_official_emulator.py --prepare-image --archive "$(NDTP_EMULATOR_ARCHIVE)"
	docker compose --profile replay stop dataset-replay
	docker compose -f docker-compose.yml -f docker-compose.official-demo.yml up -d --build --wait
	python scripts/start_official_emulator.py --archive "$(NDTP_EMULATOR_ARCHIVE)"

build:
	docker compose build

down:
	python scripts/start_official_emulator.py --stop
	docker compose --profile replay down

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

up-ndtp: up

up-dataset-replay:
	python scripts/start_official_emulator.py --stop
	docker compose -f docker-compose.yml -f docker-compose.replay.yml --profile replay up -d --build ml backend frontend dataset-replay
	python scripts/start_dataset_replay.py

replay-start:
	python scripts/start_dataset_replay.py

logs-dataset-replay:
	docker compose --profile replay logs -f dataset-replay

lint:
	cd backend && ruff check .

format:
	cd backend && ruff format .

preprocessing:
	cd ml && python -m src.offline.dataset_builder --split train

# Собирает публичные документы в docs/public/ (коммитится в Git):
# PyDoc (Sphinx) + статичный OpenAPI-файл и самодостаточный Swagger UI.
docs:
	cd backend && python -m sphinx -W --keep-going -b html docs ../docs/public/pydoc
	python scripts/export_openapi.py
	python -c "from pathlib import Path; Path('docs/public/.nojekyll').touch()"


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
	node -e "const fs = require('node:fs'); for (const path of ['frontend/dist', 'frontend/node_modules/.vite']) fs.rmSync(path, { recursive: true, force: true })"

# --- frontend: в docker ---

up-frontend:
	docker compose up -d --build frontend

up-frontend-dev:
	docker compose --profile dev up -d --build frontend-dev

logs-frontend:
	docker compose logs -f frontend
