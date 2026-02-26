.PHONY: api workers-provisioner workers-scheduler workers-reconciler test

api:
	uvicorn sparkpilot.api:app --reload --host 0.0.0.0 --port 8000

workers-provisioner:
	python -m sparkpilot.workers provisioner

workers-scheduler:
	python -m sparkpilot.workers scheduler

workers-reconciler:
	python -m sparkpilot.workers reconciler

test:
	python -m pytest -q
