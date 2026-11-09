.PHONY: init up test

# Generate a starter .env with fresh ADMIN_API_KEY + FIELD_ENCRYPTION_KEY.
init:
	python3 scripts/init_env.py

# Start the full stack (Postgres, Redis, API, worker).
up:
	docker compose up --build

# Run the backend test suite (no Docker, no API keys).
test:
	cd backend && python -m pytest tests/ -q
