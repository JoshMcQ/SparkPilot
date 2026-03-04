.PHONY: api workers-provisioner workers-scheduler workers-reconciler workers-emr-release-sync workers-cur-reconciliation test enterprise-matrix

api:
	uvicorn sparkpilot.api:app --reload --host 0.0.0.0 --port 8000

workers-provisioner:
	python -m sparkpilot.workers provisioner

workers-scheduler:
	python -m sparkpilot.workers scheduler

workers-reconciler:
	python -m sparkpilot.workers reconciler

workers-emr-release-sync:
	python -m sparkpilot.workers emr-release-sync

workers-cur-reconciliation:
	python -m sparkpilot.workers cur-reconciliation

test:
	python -m pytest -q

enterprise-matrix:
	python scripts/e2e/run_enterprise_matrix.py --manifest docs/validation/enterprise-scenario-matrix.example.json
