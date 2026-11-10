.PHONY: init up test demo report

# Generate a starter .env with fresh ADMIN_API_KEY + FIELD_ENCRYPTION_KEY.
init:
	python3 scripts/init_env.py

# Start the full stack (Postgres, Redis, API, worker).
up:
	docker compose up --build

# Run the backend test suite (no Docker, no API keys).
test:
	cd backend && python -m pytest tests/ -q

# Show a safety regression between two model versions (offline by default:
# simulated models, in-process SQLite, no Docker or keys). Opens an HTML report.
# Real models: DEMO_BEFORE_MODEL=... DEMO_AFTER_MODEL=... make demo
demo:
	python3 scripts/demo.py

# HTML report for a run or a comparison:
#   make report RUN=<run_id> [DB=demo]
#   make report COMPARE=<before_id>,<after_id> [DB=demo] [FULL=1]
# Harmful outputs are redacted; FULL=1 includes them (sensitive, warning banner).
report:
	@test -n "$(RUN)$(COMPARE)" || (echo "usage: make report RUN=<id> | COMPARE=<id1>,<id2> [DB=demo|<url>] [FULL=1]"; exit 2)
	python3 scripts/report.py $(if $(RUN),--run $(RUN)) $(if $(COMPARE),--compare $(COMPARE)) $(if $(DB),--db $(DB)) $(if $(FULL),--include-full-outputs) --open
