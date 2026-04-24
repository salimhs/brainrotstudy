.PHONY: help install dev api web test typecheck build clean docker

help:
	@echo "  install   — install Python + Node deps"
	@echo "  dev       — run API + Web concurrently (foreground)"
	@echo "  api       — run FastAPI (http://localhost:8000)"
	@echo "  web       — run Next dev server (http://localhost:3000)"
	@echo "  test      — run pytest"
	@echo "  typecheck — run tsc --noEmit"
	@echo "  build     — build the frontend"
	@echo "  docker    — build and run the all-in-one Docker image"
	@echo "  clean     — remove caches and storage"

install:
	cd server && uv venv --python 3.11 --quiet && uv pip install -e '.[dev]'
	cd web && npm install

api:
	cd server && uv run brainrotstudy --reload

web:
	cd web && npm run dev

dev:
	@echo "Starting API and Web. Ctrl+C to stop."
	@$(MAKE) -j 2 api web

test:
	cd server && uv run pytest -q

typecheck:
	cd web && npm run typecheck

build:
	cd web && npm run build

docker:
	docker build -t brainrotstudy:latest .
	docker run --rm -it --env-file .env -p 3000:3000 -p 8000:8000 \
		-v $(PWD)/storage:/app/storage brainrotstudy:latest

clean:
	rm -rf server/.venv server/.pytest_cache server/**/__pycache__ \
	       web/.next web/node_modules storage
