# Job Template And Run Field Guide (BYOC-Lite)

This page is the demo-safe reference for creating a job template and submitting a run without rediscovering settings live.

It includes the exact profile that succeeded in live AWS on March 17, 2026.

## 1. Pre-demo readiness checks (required)

Run these before any customer/investor demo:

1. Environment is `ready` in `/environments`.
2. Preflight for target environment returns `ready=true`.
3. EKS has enough nodes for requested driver/executor resources.
4. No stale active run consuming cluster capacity.
5. Artifact bucket + input object exist before submit.

PowerShell checks:

```powershell
kubectl get nodes
kubectl get pods -n <namespace>
```

```powershell
python -m sparkpilot.cli env-preflight --environment-id <environment-id> --base-url http://127.0.0.1:8000
```

```powershell
python -m awscli s3 ls s3://<bucket>/jobs/
python -m awscli s3 ls s3://<bucket>/input/
```

## 2. Known-good job template (worked profile)

Use this as baseline for demos, then change only one thing at a time.

- `Environment`: `us-east-1 / sparkpilot-demo-2 (4c7d381a)`
- `Job Name`: `demo-job-4`
- `Artifact URI`: `s3://sparkpilot-live-787587782916-20260224203702/jobs/sparkpilot_demo_job.py`
- `Artifact Digest`: `sha256:placeholder`
- `Entrypoint`: `main`
- `Retry Max Attempts`: `1`
- `Timeout (seconds)`: `1200`
- `Args (one per line)`:
  - `s3://sparkpilot-live-787587782916-20260224203702/input/events.json`
  - `s3://sparkpilot-live-787587782916-20260224203702/output/demo-job-4-<timestamp>/`
- `Spark Conf (key=value per line)`:

```text
spark.executor.instances=1
spark.executor.memory=1g
spark.driver.memory=1g
```

Important:

- `spark.executor.instances=2` caused capacity starvation during this run cycle.
- The demo script requires exactly two args: `<input_path> <output_path>`.
- Do not reuse the same output prefix between runs.

## 3. Run submit values (demo-safe)

Use conservative resources unless cluster capacity is verified:

- `Driver vCPU`: `1`
- `Driver Memory (GB)`: `1` or `2`
- `Executor vCPU`: `1`
- `Executor Memory (GB)`: `1` or `2`
- `Executor Instances`: `1`
- `Timeout (seconds)`: `1800`

## 4. Immediate success verification (do not rely only on UI)

After submit, confirm success from AWS directly:

```powershell
python -m awscli emr-containers describe-job-run `
  --virtual-cluster-id <virtual-cluster-id> `
  --id <emr-job-run-id> `
  --region us-east-1 `
  --profile default `
  --query "jobRun.[state,createdAt,finishedAt,failureReason,stateDetails]" `
  --output table
```

```powershell
python -m awscli s3 ls s3://<bucket>/output/<prefix>/ --recursive --summarize --region us-east-1 --profile default
```

Success criteria:

- EMR state is `COMPLETED`.
- Output prefix contains `_SUCCESS` and at least one output data file.

## 5. Fast failure map (what failed this cycle)

- `NoSuchBucket` in run failure details:
  - Artifact/input bucket path is wrong. Validate bucket/object exists before submit.
- Run stays `accepted` with no pod assignment:
  - Cluster lacks capacity. Scale nodegroup, wait for nodes, then resubmit.
- `Initial job has not accepted any resources`:
  - Executors cannot schedule. Lower executor count/memory or increase nodes.
- `Usage: sparkpilot_demo_job.py <input_path> <output_path>`:
  - Job args are wrong; pass exactly two positional args.

## 6. Demo discipline (reduce blast radius)

1. Keep one active run at a time during demos.
2. Cancel stale active runs before starting new run.
3. Use timestamped output prefix each run.
4. Save `run_id`, `emr_job_run_id`, output prefix, and EMR terminal state in notes immediately.
