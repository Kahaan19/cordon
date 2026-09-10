.PHONY: ingest audit test

export PYTHONPATH := src:.

ingest:
	uv run python -m cordon.ingest

audit:
	uv run python -m cordon.brand_audit

test:
	uv run pytest -v
