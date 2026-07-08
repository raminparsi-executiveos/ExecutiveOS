# Simple Makefile for common development tasks
.PHONY: help build-backend run-backend build-frontend start-frontend test

help:
	@echo "Available targets:"
	@echo "  build-backend   Build the backend Docker image"
	@echo "  run-backend     Run the backend Docker image locally (port 8000)"
	@echo "  build-frontend  Build the frontend static bundle (Vite)"
	@echo "  start-frontend  Run the frontend dev server (Vite)"
	@echo "  test            Run backend tests with pytest"

build-backend:
	docker build -t executiveos-backend -f backend/Dockerfile .

run-backend: build-backend
	docker run --rm -p 8000:8000 -e PORT=8000 executiveos-backend

build-frontend:
	cd frontend && npm ci --silent && npm run build

start-frontend:
	cd frontend && npm run dev

test:
	python -m pytest -q
