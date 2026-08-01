.PHONY: test test-shared test-admin test-gateway test-worker test-integration lint format

test: test-shared test-admin test-gateway test-worker

test-shared:
	python -m pytest tests/shared -q

test-admin:
	python -m pytest tests/admin -q

test-gateway:
	python -m pytest tests/gateway -q

test-worker:
	python -m pytest tests/worker -q

test-integration:
	python -m pytest tests/integration -v

lint:
	ruff check .

format:
	ruff format .
