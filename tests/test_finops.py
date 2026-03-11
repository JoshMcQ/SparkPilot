from datetime import UTC, datetime, timedelta
import json
import os
from types import SimpleNamespace
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

os.environ.setdefault("SPARKPILOT_DATABASE_URL", "sqlite:///./sparkpilot_test.db")

from sparkpilot.api import app  # noqa: E402
from sparkpilot.config import get_settings  # noqa: E402
from sparkpilot.db import Base, SessionLocal, engine, init_db  # noqa: E402
from sparkpilot.models import CostAllocation, Environment, Run, TeamBudget  # noqa: E402
from sparkpilot.cost_center import resolve_cost_center_for_environment  # noqa: E402
from sparkpilot.services.finops import (
    _fetch_pricing_api_snapshot,
    _parse_athena_cost_rows,
    _reset_pricing_cache,
    _resolve_runtime_pricing,
)  # noqa: E402
from sparkpilot.services import _build_preflight, process_cur_reconciliation_once, process_provisioning_once, process_reconciler_once, process_scheduler_once  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    init_db()
    _reset_pricing_cache()


def _create_ready_env(client: TestClient, suffix: str) -> tuple[dict, dict]:
    tenant = client.post(
        "/v1/tenants",
        json={"name": f"FinOps Tenant {suffix}"},
        headers={"Idempotency-Key": f"tenant-finops-{suffix}"},
    ).json()
    op = client.post(
        "/v1/environments",
        json={
            "tenant_id": tenant["id"],
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
            "eks_namespace": "sparkpilot-finops-team",
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        },
        headers={"Idempotency-Key": f"env-finops-{suffix}"},
    ).json()
    with SessionLocal() as db:
        process_provisioning_once(db)
    return tenant, op


def test_team_budget_endpoints_and_preflight_budget_fail() -> None:
    client = TestClient(app)
    tenant, op = _create_ready_env(client, "budget")
    team = tenant["id"]

    create_budget = client.post(
        "/v1/team-budgets",
        json={
            "team": team,
            "monthly_budget_usd_micros": 1_000,
            "warn_threshold_pct": 80,
            "block_threshold_pct": 100,
        },
    )
    assert create_budget.status_code == 201

    get_budget = client.get(f"/v1/team-budgets/{team}")
    assert get_budget.status_code == 200
    assert get_budget.json()["team"] == team

    with SessionLocal() as db:
        env = db.get(Environment, op["environment_id"])
        assert env is not None
        db.add(
            CostAllocation(
                run_id="run-budget-1",
                environment_id=env.id,
                tenant_id=env.tenant_id,
                team=team,
                cost_center=env.eks_namespace or env.id,
                billing_period=datetime.now(UTC).strftime("%Y-%m"),
                estimated_vcpu_seconds=10,
                estimated_memory_gb_seconds=10,
                estimated_cost_usd_micros=2_000,
                actual_cost_usd_micros=2_000,
            )
        )
        db.commit()

    preflight = client.get(f"/v1/environments/{op['environment_id']}/preflight")
    assert preflight.status_code == 200
    team_budget = next(item for item in preflight.json()["checks"] if item["code"] == "team_budget")
    assert team_budget["status"] == "fail"


def test_showback_endpoint_returns_allocations_from_run_usage() -> None:
    client = TestClient(app)
    tenant, op = _create_ready_env(client, "showback")

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": op["environment_id"],
            "name": "job-showback",
            "artifact_uri": "s3://bucket/job.jar",
            "artifact_digest": "sha256:def456",
            "entrypoint": "com.acme.Main",
        },
        headers={"Idempotency-Key": "job-showback"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={
            "requested_resources": {
                "driver_vcpu": 1,
                "driver_memory_gb": 4,
                "executor_vcpu": 1,
                "executor_memory_gb": 4,
                "executor_instances": 1,
            }
        },
        headers={"Idempotency-Key": "run-showback"},
    ).json()

    with SessionLocal() as db:
        process_scheduler_once(db)
        row = db.get(Run, run["id"])
        assert row is not None
        row.state = "accepted"
        row.started_at = datetime.now(UTC) - timedelta(minutes=10)
        db.commit()
        process_reconciler_once(db)

    period = datetime.now(UTC).strftime("%Y-%m")
    costs = client.get(f"/v1/costs?team={tenant['id']}&period={period}")
    assert costs.status_code == 200
    payload = costs.json()
    assert payload["team"] == tenant["id"]
    assert payload["period"] == period
    assert payload["total_effective_cost_usd_micros"] > 0
    assert any(item["run_id"] == run["id"] for item in payload["items"])

    paged = client.get(f"/v1/costs?team={tenant['id']}&period={period}&limit=1&offset=0")
    assert paged.status_code == 200
    assert len(paged.json()["items"]) == 1


def test_cost_center_policy_mapping_applies_to_recorded_allocation(monkeypatch) -> None:
    monkeypatch.setenv(
        "SPARKPILOT_COST_CENTER_POLICY_JSON",
        '{"by_namespace":{"sparkpilot-finops-team":"cc-finops-prod"}}',
    )
    get_settings.cache_clear()

    client = TestClient(app)
    tenant, op = _create_ready_env(client, "cost-center")

    job = client.post(
        "/v1/jobs",
        json={
            "environment_id": op["environment_id"],
            "name": "job-cost-center",
            "artifact_uri": "s3://bucket/job.jar",
            "artifact_digest": "sha256:cc",
            "entrypoint": "com.acme.Main",
        },
        headers={"Idempotency-Key": "job-cost-center"},
    ).json()
    run = client.post(
        f"/v1/jobs/{job['id']}/runs",
        json={},
        headers={"Idempotency-Key": "run-cost-center"},
    ).json()

    with SessionLocal() as db:
        process_scheduler_once(db)
        row = db.get(Run, run["id"])
        assert row is not None
        row.state = "accepted"
        row.started_at = datetime.now(UTC) - timedelta(minutes=5)
        db.commit()
        process_reconciler_once(db)
        allocation = db.execute(select(CostAllocation).where(CostAllocation.run_id == run["id"])).scalar_one()
        assert allocation.cost_center == "cc-finops-prod"

    # Pure resolver check for virtual-cluster precedence over namespace mapping.
    env = SimpleNamespace(
        id=op["environment_id"],
        tenant_id=tenant["id"],
        eks_namespace="sparkpilot-finops-team",
        emr_virtual_cluster_id="vc-123",
    )
    monkeypatch.setenv(
        "SPARKPILOT_COST_CENTER_POLICY_JSON",
        (
            '{"by_namespace":{"sparkpilot-finops-team":"cc-namespace"},'
            '"by_virtual_cluster_id":{"vc-123":"cc-virtual-cluster"}}'
        ),
    )
    get_settings.cache_clear()
    resolved = resolve_cost_center_for_environment(settings=get_settings(), environment=env)
    assert resolved == "cc-virtual-cluster"

    get_settings.cache_clear()


def test_cur_reconciliation_worker_updates_actual_cost(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_CUR_ATHENA_DATABASE", "cur_db")
    monkeypatch.setenv("SPARKPILOT_CUR_ATHENA_TABLE", "cur_table")
    monkeypatch.setenv("SPARKPILOT_CUR_ATHENA_OUTPUT_LOCATION", "s3://cur-results/")
    monkeypatch.setenv("SPARKPILOT_CUR_ATHENA_WORKGROUP", "primary")
    get_settings.cache_clear()

    run_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(
            CostAllocation(
                run_id=run_id,
                environment_id="env-1",
                tenant_id="tenant-1",
                team="tenant-1",
                cost_center="cc-1",
                billing_period=datetime.now(UTC).strftime("%Y-%m"),
                estimated_vcpu_seconds=100,
                estimated_memory_gb_seconds=200,
                estimated_cost_usd_micros=12_000,
            )
        )
        db.commit()

    class _FakeAthenaClient:
        def start_query_execution(self, **_kwargs):
            return {"QueryExecutionId": "q-1"}

        def get_query_execution(self, **_kwargs):
            return {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}

        def get_query_results(self, **_kwargs):
            return {
                "ResultSet": {
                    "Rows": [
                        {"Data": [{"VarCharValue": "run_id"}, {"VarCharValue": "cost_usd"}]},
                        {"Data": [{"VarCharValue": run_id}, {"VarCharValue": "0.25"}]},
                    ]
                }
            }

    monkeypatch.setattr("sparkpilot.services.boto3.client", lambda *_args, **_kwargs: _FakeAthenaClient())

    with SessionLocal() as db:
        changed = process_cur_reconciliation_once(db)
        assert changed == 1
        item = db.execute(select(CostAllocation).where(CostAllocation.run_id == run_id)).scalar_one()
        assert item.actual_cost_usd_micros == 250_000
        assert item.cur_reconciled_at is not None

    get_settings.cache_clear()


def test_cur_reconciliation_rejects_invalid_identifier(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_CUR_ATHENA_DATABASE", "cur_db")
    monkeypatch.setenv("SPARKPILOT_CUR_ATHENA_TABLE", "cur_table")
    monkeypatch.setenv("SPARKPILOT_CUR_ATHENA_OUTPUT_LOCATION", "s3://cur-results/")
    monkeypatch.setenv("SPARKPILOT_CUR_RUN_ID_COLUMN", "run_id;DROP_TABLE")
    get_settings.cache_clear()

    with SessionLocal() as db:
        db.add(
            CostAllocation(
                run_id=str(uuid.uuid4()),
                environment_id="env-1",
                tenant_id="tenant-1",
                team="tenant-1",
                cost_center="cc-1",
                billing_period=datetime.now(UTC).strftime("%Y-%m"),
                estimated_vcpu_seconds=100,
                estimated_memory_gb_seconds=200,
                estimated_cost_usd_micros=12_000,
            )
        )
        db.commit()
        with pytest.raises(ValueError) as exc_info:
            process_cur_reconciliation_once(db)
        assert "Invalid Athena identifier" in str(exc_info.value)

    get_settings.cache_clear()


def test_cur_reconciliation_rejects_invalid_run_ids(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_CUR_ATHENA_DATABASE", "cur_db")
    monkeypatch.setenv("SPARKPILOT_CUR_ATHENA_TABLE", "cur_table")
    monkeypatch.setenv("SPARKPILOT_CUR_ATHENA_OUTPUT_LOCATION", "s3://cur-results/")
    get_settings.cache_clear()

    with SessionLocal() as db:
        db.add(
            CostAllocation(
                run_id="run-cur-1",
                environment_id="env-1",
                tenant_id="tenant-1",
                team="tenant-1",
                cost_center="cc-1",
                billing_period=datetime.now(UTC).strftime("%Y-%m"),
                estimated_vcpu_seconds=100,
                estimated_memory_gb_seconds=200,
                estimated_cost_usd_micros=12_000,
            )
        )
        db.commit()
        with pytest.raises(ValueError) as exc_info:
            process_cur_reconciliation_once(db)
        assert "Invalid run_id values for CUR reconciliation" in str(exc_info.value)

    get_settings.cache_clear()


def test_build_preflight_uses_passed_db_session_for_budget(monkeypatch) -> None:
    client = TestClient(app)
    tenant, op = _create_ready_env(client, "preflight-db")
    team = tenant["id"]

    with SessionLocal() as db:
        env = db.get(Environment, op["environment_id"])
        assert env is not None
        db.add(
            TeamBudget(
                team=team,
                monthly_budget_usd_micros=1_000_000,
                warn_threshold_pct=80,
                block_threshold_pct=100,
            )
        )
        db.commit()

        def _forbidden_session_local():
            raise AssertionError("SessionLocal should not be invoked when _build_preflight receives db.")

        monkeypatch.setattr("sparkpilot.services.preflight.SessionLocal", _forbidden_session_local)
        payload = _build_preflight(env, db=db)

    team_budget = next(item for item in payload["checks"] if item["code"] == "team_budget")
    assert team_budget["status"] == "pass"


def test_pricing_api_snapshot_derives_rates_from_ec2_samples(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv(
        "SPARKPILOT_EMR_EXECUTION_ROLE_ARN",
        "arn:aws:iam::123456789012:role/SparkPilotExecRole",
    )
    monkeypatch.setenv("SPARKPILOT_PRICING_SOURCE", "aws_pricing_api")
    monkeypatch.setenv("SPARKPILOT_AWS_REGION", "us-east-1")
    get_settings.cache_clear()

    catalog = {
        "c6i.xlarge": {"price": 0.17, "vcpu": "4", "memory": "8 GiB"},
        "r6i.xlarge": {"price": 0.25, "vcpu": "4", "memory": "32 GiB"},
        "c6g.xlarge": {"price": 0.136, "vcpu": "4", "memory": "8 GiB"},
        "r6g.xlarge": {"price": 0.20, "vcpu": "4", "memory": "32 GiB"},
    }

    class _FakePricingPaginator:
        def paginate(self, **kwargs):
            filters = kwargs.get("Filters", [])
            field_values = {item["Field"]: item["Value"] for item in filters}
            instance_type = field_values.get("instanceType")
            record = catalog.get(instance_type)
            if record is None:
                return [{"PriceList": []}]
            payload = {
                "product": {
                    "attributes": {
                        "instanceType": instance_type,
                        "regionCode": "us-east-1",
                        "vcpu": record["vcpu"],
                        "memory": record["memory"],
                    }
                },
                "terms": {
                    "OnDemand": {
                        "term": {
                            "priceDimensions": {
                                "dim": {
                                    "unit": "Hrs",
                                    "pricePerUnit": {"USD": str(record["price"])},
                                }
                            }
                        }
                    }
                },
            }
            return [{"PriceList": [json.dumps(payload)]}]

    class _FakePricingClient:
        @staticmethod
        def get_paginator(name: str):
            assert name == "get_products"
            return _FakePricingPaginator()

    monkeypatch.setattr(
        "sparkpilot.services.finops.boto3.client",
        lambda service_name, **_kwargs: _FakePricingClient() if service_name == "pricing" else None,
    )

    snapshot = _fetch_pricing_api_snapshot(get_settings())
    assert snapshot.source.startswith("aws_pricing_api:")
    assert snapshot.vcpu_usd_per_second == pytest.approx(0.0358333333 / 3600.0, rel=1e-6)
    assert snapshot.memory_gb_usd_per_second == pytest.approx(0.0033333333 / 3600.0, rel=1e-6)
    assert snapshot.arm64_discount_pct == pytest.approx(20.0, rel=1e-6)
    assert snapshot.mixed_discount_pct == pytest.approx(10.0, rel=1e-6)
    get_settings.cache_clear()


def test_pricing_auto_mode_falls_back_to_static_when_pricing_api_fails(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv(
        "SPARKPILOT_EMR_EXECUTION_ROLE_ARN",
        "arn:aws:iam::123456789012:role/SparkPilotExecRole",
    )
    monkeypatch.setenv("SPARKPILOT_PRICING_SOURCE", "auto")
    monkeypatch.setenv("SPARKPILOT_PRICING_VCPU_USD_PER_SECOND", "0.00002")
    monkeypatch.setenv("SPARKPILOT_PRICING_MEMORY_GB_USD_PER_SECOND", "0.000003")
    monkeypatch.setenv("SPARKPILOT_PRICING_ARM64_DISCOUNT_PCT", "15")
    monkeypatch.setenv("SPARKPILOT_PRICING_MIXED_DISCOUNT_PCT", "7.5")
    get_settings.cache_clear()
    _reset_pricing_cache()

    monkeypatch.setattr(
        "sparkpilot.services.finops._fetch_pricing_api_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("pricing API unavailable")),
    )
    snapshot = _resolve_runtime_pricing(get_settings())
    assert snapshot.source == "static-fallback"
    assert snapshot.vcpu_usd_per_second == pytest.approx(0.00002)
    assert snapshot.memory_gb_usd_per_second == pytest.approx(0.000003)
    assert snapshot.arm64_discount_pct == pytest.approx(15.0)
    assert snapshot.mixed_discount_pct == pytest.approx(7.5)
    get_settings.cache_clear()


def test_pricing_api_mode_raises_when_lookup_fails(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv(
        "SPARKPILOT_EMR_EXECUTION_ROLE_ARN",
        "arn:aws:iam::123456789012:role/SparkPilotExecRole",
    )
    monkeypatch.setenv("SPARKPILOT_PRICING_SOURCE", "aws_pricing_api")
    get_settings.cache_clear()
    _reset_pricing_cache()

    monkeypatch.setattr(
        "sparkpilot.services.finops._fetch_pricing_api_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("pricing API unavailable")),
    )
    with pytest.raises(ValueError, match="pricing API unavailable"):
        _resolve_runtime_pricing(get_settings())
    get_settings.cache_clear()


def test_parse_athena_cost_rows_uses_decimal_rounding_and_skips_headers() -> None:
    rows = [
        {"Data": [{"VarCharValue": "run_id"}, {"VarCharValue": "cost_usd"}]},
        {"Data": [{"VarCharValue": "run-1"}, {"VarCharValue": "0.0000015"}]},
        {"Data": [{"VarCharValue": "run-2"}, {"VarCharValue": "0.0000014"}]},
        {"Data": [{"VarCharValue": "run-2"}, {"VarCharValue": "0.0000014"}]},
        {"Data": [{"VarCharValue": "run-3"}, {"VarCharValue": "not-a-number"}]},
    ]
    result = _parse_athena_cost_rows(rows)
    assert result["run-1"] == 2
    assert result["run-2"] == 2
    assert "run-3" not in result


def test_cur_reconciliation_worker_handles_paginated_results(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_CUR_ATHENA_DATABASE", "cur_db")
    monkeypatch.setenv("SPARKPILOT_CUR_ATHENA_TABLE", "cur_table")
    monkeypatch.setenv("SPARKPILOT_CUR_ATHENA_OUTPUT_LOCATION", "s3://cur-results/")
    monkeypatch.setenv("SPARKPILOT_CUR_ATHENA_WORKGROUP", "primary")
    get_settings.cache_clear()

    run_id_1 = str(uuid.uuid4())
    run_id_2 = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(
            CostAllocation(
                run_id=run_id_1,
                environment_id="env-1",
                tenant_id="tenant-1",
                team="tenant-1",
                cost_center="cc-1",
                billing_period=datetime.now(UTC).strftime("%Y-%m"),
                estimated_vcpu_seconds=100,
                estimated_memory_gb_seconds=200,
                estimated_cost_usd_micros=12_000,
            )
        )
        db.add(
            CostAllocation(
                run_id=run_id_2,
                environment_id="env-1",
                tenant_id="tenant-1",
                team="tenant-1",
                cost_center="cc-2",
                billing_period=datetime.now(UTC).strftime("%Y-%m"),
                estimated_vcpu_seconds=120,
                estimated_memory_gb_seconds=250,
                estimated_cost_usd_micros=15_000,
            )
        )
        db.commit()

    class _FakeAthenaClient:
        def start_query_execution(self, **_kwargs):
            return {"QueryExecutionId": "q-1"}

        def get_query_execution(self, **_kwargs):
            return {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}

        def get_query_results(self, **kwargs):
            next_token = kwargs.get("NextToken")
            if next_token is None:
                return {
                    "ResultSet": {
                        "Rows": [
                            {"Data": [{"VarCharValue": "run_id"}, {"VarCharValue": "cost_usd"}]},
                            {"Data": [{"VarCharValue": run_id_1}, {"VarCharValue": "0.10"}]},
                        ]
                    },
                    "NextToken": "page-2",
                }
            return {
                "ResultSet": {
                    "Rows": [
                        {"Data": [{"VarCharValue": run_id_2}, {"VarCharValue": "0.25"}]},
                    ]
                }
            }

    monkeypatch.setattr("sparkpilot.services.finops.boto3.client", lambda *_args, **_kwargs: _FakeAthenaClient())

    with SessionLocal() as db:
        changed = process_cur_reconciliation_once(db)
        assert changed == 2
        row1 = db.execute(select(CostAllocation).where(CostAllocation.run_id == run_id_1)).scalar_one()
        row2 = db.execute(select(CostAllocation).where(CostAllocation.run_id == run_id_2)).scalar_one()
        assert row1.actual_cost_usd_micros == 100_000
        assert row2.actual_cost_usd_micros == 250_000
        assert row1.cur_reconciled_at is not None
        assert row2.cur_reconciled_at is not None

    get_settings.cache_clear()
