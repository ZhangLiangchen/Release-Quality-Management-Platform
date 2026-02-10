SHELL := /bin/zsh
NPM_REGISTRY ?= https://registry.npmmirror.com/
PIP_CONFIG_FILE ?= ./pip.conf

.PHONY: frontend-install frontend-dev frontend-build frontend-test
.PHONY: backend-venv backend-install backend-run backend-test
.PHONY: docker-up docker-down

frontend-install:
	cd frontend && NPM_CONFIG_REGISTRY=$(NPM_REGISTRY) NPM_CONFIG_STRICT_SSL=false npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend-test:
	cd frontend && npm run test -- --run

backend-venv:
	cd backend && python3 -m venv .venv

backend-install: backend-venv
	cd backend && source .venv/bin/activate && PIP_CONFIG_FILE=$(PIP_CONFIG_FILE) pip install --upgrade pip && PIP_CONFIG_FILE=$(PIP_CONFIG_FILE) pip install -r requirements-dev.txt

backend-run:
	cd backend && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

backend-test:
	cd backend && source .venv/bin/activate && pytest -q

docker-up:
	docker compose -f deploy/docker-compose.yml up --build

docker-down:
	docker compose -f deploy/docker-compose.yml down -v
