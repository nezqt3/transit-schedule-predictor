.PHONY: up down build logs test docs features train submit run-online

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
	cd backend && sphinx-build -b html docs docs/_build/html
