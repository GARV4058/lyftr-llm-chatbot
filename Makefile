.PHONY: up down build logs test clean help

help:
	@echo "Available commands:"
	@echo "  make up      - Build and start full stack in Docker (Backend: 8000, Frontend: 3000)"
	@echo "  make down    - Stop and remove all running containers"
	@echo "  make build   - Build Docker container images"
	@echo "  make logs    - Stream container logs"
	@echo "  make test    - Run backend pytest suite"
	@echo "  make clean   - Remove containers, volumes, and temporary files"

up:
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

test:
	docker compose run --rm backend pytest tests -v

clean:
	docker compose down -v --remove-orphans
