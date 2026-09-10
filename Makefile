.PHONY: ingest audit taxonomy taxonomy-finalize test

export PYTHONPATH := src:.

ingest:
	uv run python -m cordon.ingest

audit:
	uv run python -m cordon.brand_audit

taxonomy:
	uv run python -m cordon.taxonomy

taxonomy-finalize:
	uv run python -m cordon.taxonomy_finalize \
		--merge-map taxonomy/merge_map.yaml \
		--notes taxonomy/boundary_notes.yaml

test:
	uv run pytest -v
