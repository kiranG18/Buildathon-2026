PY ?= python

.PHONY: dev worker db seed reset test lint schemas

db:
	docker compose up -d db

dev:
	$(PY) -m uvicorn backend.main:app --reload --port 8000

worker:
	$(PY) -m backend.worker

seed:
	$(PY) scripts/load_seed.py

reset:
	$(PY) scripts/reset_demo.py

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check .

schemas:
	$(PY) scripts/export_schemas.py
