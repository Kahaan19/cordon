.PHONY: ingest audit taxonomy taxonomy-finalize index playbook sample label agent baselines judge judge-validate calibrate evaluate report bad-sample bad-label test

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

index:
	uv run python -m cordon.index

playbook:
	uv run python -m cordon.playbook

sample:
	uv run python -m cordon.sampler

label:
	uv run python -m cordon.labeler

agent:
	uv run python -m cordon.agent --n 10

baselines:
	uv run python -m cordon.baselines --n 10

judge:
	uv run python -m cordon.judge

judge-validate:
	uv run python -m cordon.judge_validation

calibrate:
	uv run python -m cordon.calibrate

evaluate:
	uv run python -m cordon.evaluate

report:
	uv run python -m cordon.report

bad-sample:
	uv run python -m cordon.bad_to_autosend_sampler

bad-label:
	uv run python -m cordon.bad_to_autosend_labeler

test:
	uv run pytest -v
