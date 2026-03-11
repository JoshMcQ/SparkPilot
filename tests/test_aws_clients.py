from botocore.exceptions import ClientError
import json
import pytest
from types import SimpleNamespace

from sparkpilot.aws_clients import CloudWatchLogsProxy, EmrEksClient, _emr_job_run_name
from sparkpilot.config import get_settings


def test_fetch_lines_returns_empty_on_client_error(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    get_settings.cache_clear()

    def _raise_client_error(*_args, **_kwargs):
        raise ClientError(
            {
                "Error": {
                    "Code": "ResourceNotFoundException",
                    "Message": "The specified log group does not exist.",
                }
            },
            "FilterLogEvents",
        )

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", _raise_client_error)

    proxy = CloudWatchLogsProxy()
    lines = proxy.fetch_lines(
        role_arn="arn:aws:iam::123456789012:role/TestRole",
        region="us-east-1",
        log_group="/sparkpilot/runs/test",
        log_stream_prefix="run/attempt-1",
        limit=20,
    )
    assert lines == []

    # Ensure later tests pick up their own environment settings.
    get_settings.cache_clear()


def test_fetch_lines_raises_on_non_resource_not_found_client_error(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    get_settings.cache_clear()

    def _raise_client_error(*_args, **_kwargs):
        raise ClientError(
            {
                "Error": {
                    "Code": "AccessDeniedException",
                    "Message": "User is not authorized to perform logs:FilterLogEvents",
                }
            },
            "FilterLogEvents",
        )

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", _raise_client_error)

    proxy = CloudWatchLogsProxy()
    with pytest.raises(ClientError):
        proxy.fetch_lines(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            region="us-east-1",
            log_group="/sparkpilot/runs/test",
            log_stream_prefix="run/attempt-1",
            limit=20,
        )

    get_settings.cache_clear()


def test_update_execution_role_trust_policy_success(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv(
        "SPARKPILOT_EMR_EXECUTION_ROLE_ARN",
        "arn:aws:iam::123456789012:role/platform/SparkPilotEmrExecutionRole",
    )
    get_settings.cache_clear()

    updated_policy = {}

    class _FakeEksClient:
        def describe_cluster(self, **kwargs):
            assert kwargs["name"] == "customer-shared"
            return {
                "cluster": {
                    "identity": {
                        "oidc": {
                            "issuer": "https://oidc.eks.us-east-1.amazonaws.com/id/ABC123",
                        }
                    }
                }
            }

    class _FakeIamClient:
        def get_role(self, **kwargs):
            assert kwargs["RoleName"] == "SparkPilotEmrExecutionRole"
            return {
                "Role": {
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [],
                    }
                }
            }

        def update_assume_role_policy(self, **kwargs):
            assert kwargs["RoleName"] == "SparkPilotEmrExecutionRole"
            updated_policy.update(json.loads(kwargs["PolicyDocument"]))

    class _FakeSession:
        def client(self, service_name, region_name=None):
            if service_name == "eks":
                assert region_name == "us-east-1"
                return _FakeEksClient()
            if service_name == "iam":
                return _FakeIamClient()
            raise AssertionError(f"Unexpected service: {service_name}")

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", lambda *_args, **_kwargs: _FakeSession())

    environment = SimpleNamespace(
        eks_cluster_arn="arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
        eks_namespace="sparkpilot-team",
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
    )
    result = EmrEksClient().update_execution_role_trust_policy(environment)
    assert result["updated"] is True
    assert result["cluster_name"] == "customer-shared"
    assert result["namespace"] == "sparkpilot-team"
    assert result["role_name"] == "SparkPilotEmrExecutionRole"
    assert result["provider_arn"] == "arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/ABC123"
    # Verify the trust policy was updated with the correct statement
    assert len(updated_policy["Statement"]) == 1
    stmt = updated_policy["Statement"][0]
    assert stmt["Action"] == "sts:AssumeRoleWithWebIdentity"
    assert "oidc.eks.us-east-1.amazonaws.com/id/ABC123:sub" in stmt["Condition"]["StringLike"]
    get_settings.cache_clear()


def test_update_execution_role_trust_policy_access_denied_message_is_actionable(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv(
        "SPARKPILOT_EMR_EXECUTION_ROLE_ARN",
        "arn:aws:iam::123456789012:role/SparkPilotEmrExecutionRole",
    )
    get_settings.cache_clear()

    class _FakeEksClient:
        def describe_cluster(self, **_kwargs):
            return {
                "cluster": {
                    "identity": {
                        "oidc": {
                            "issuer": "https://oidc.eks.us-east-1.amazonaws.com/id/ABC123",
                        }
                    }
                }
            }

    class _FakeIamClient:
        def get_role(self, **_kwargs):
            return {
                "Role": {
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [],
                    }
                }
            }

        def update_assume_role_policy(self, **_kwargs):
            raise ClientError(
                {
                    "Error": {
                        "Code": "AccessDeniedException",
                        "Message": "User is not authorized to perform iam:UpdateAssumeRolePolicy",
                    }
                },
                "UpdateAssumeRolePolicy",
            )

    class _FakeSession:
        def client(self, service_name, region_name=None):
            if service_name == "eks":
                return _FakeEksClient()
            if service_name == "iam":
                return _FakeIamClient()
            raise AssertionError(f"Unexpected service: {service_name}")

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", lambda *_args, **_kwargs: _FakeSession())

    environment = SimpleNamespace(
        eks_cluster_arn="arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
        eks_namespace="sparkpilot-team",
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
    )
    with pytest.raises(ValueError) as exc_info:
        EmrEksClient().update_execution_role_trust_policy(environment)
    message = str(exc_info.value)
    assert "iam:UpdateAssumeRolePolicy" in message
    assert "aws emr-containers update-role-trust-policy" in message
    assert "--cluster-name customer-shared" in message
    assert "--namespace sparkpilot-team" in message
    get_settings.cache_clear()


def test_check_oidc_provider_association_returns_false_when_provider_missing(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    get_settings.cache_clear()

    class _FakeEksClient:
        def describe_cluster(self, **kwargs):
            assert kwargs["name"] == "customer-shared"
            return {
                "cluster": {
                    "identity": {
                        "oidc": {
                            "issuer": "https://oidc.eks.us-east-1.amazonaws.com/id/CLUSTERID",
                        }
                    }
                }
            }

    class _FakeIamClient:
        def get_open_id_connect_provider(self, **kwargs):
            assert kwargs["OpenIDConnectProviderArn"] == (
                "arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/CLUSTERID"
            )
            raise ClientError(
                {"Error": {"Code": "NoSuchEntity", "Message": "provider not found"}},
                "GetOpenIDConnectProvider",
            )

    class _FakeSession:
        def client(self, service_name, region_name=None):
            if service_name == "eks":
                assert region_name == "us-east-1"
                return _FakeEksClient()
            if service_name == "iam":
                return _FakeIamClient()
            raise AssertionError(f"Unexpected service: {service_name}")

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", lambda *_args, **_kwargs: _FakeSession())

    environment = SimpleNamespace(
        eks_cluster_arn="arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
        eks_namespace="sparkpilot-team",
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
    )
    result = EmrEksClient().check_oidc_provider_association(environment)
    assert result["associated"] is False
    assert result["cluster_name"] == "customer-shared"
    assert result["oidc_provider_arn"] == (
        "arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/CLUSTERID"
    )
    get_settings.cache_clear()


def test_check_oidc_provider_association_access_denied_is_actionable(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    get_settings.cache_clear()

    class _FakeEksClient:
        def describe_cluster(self, **_kwargs):
            raise ClientError(
                {
                    "Error": {
                        "Code": "AccessDeniedException",
                        "Message": "User is not authorized to perform eks:DescribeCluster",
                    }
                },
                "DescribeCluster",
            )

    class _FakeSession:
        def client(self, service_name, region_name=None):
            assert service_name == "eks"
            assert region_name == "us-east-1"
            return _FakeEksClient()

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", lambda *_args, **_kwargs: _FakeSession())

    environment = SimpleNamespace(
        eks_cluster_arn="arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
        eks_namespace="sparkpilot-team",
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
    )
    with pytest.raises(ValueError) as exc_info:
        EmrEksClient().check_oidc_provider_association(environment)
    message = str(exc_info.value)
    assert "eks:DescribeCluster" in message
    assert "iam:GetOpenIDConnectProvider" in message
    assert "aws eks describe-cluster" in message
    assert "--name customer-shared" in message
    get_settings.cache_clear()


def test_start_job_run_adds_chargeback_tags_and_labels(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv("SPARKPILOT_LOG_GROUP_PREFIX", "/sparkpilot/runs")
    monkeypatch.setenv("SPARKPILOT_EMR_RELEASE_LABEL", "emr-6.15.0-latest")
    monkeypatch.setenv(
        "SPARKPILOT_EMR_EXECUTION_ROLE_ARN",
        "arn:aws:iam::123456789012:role/SparkPilotEmrExecutionRole",
    )
    monkeypatch.setenv(
        "SPARKPILOT_COST_CENTER_POLICY_JSON",
        '{"by_namespace":{"sparkpilot-team-a":"cc-analytics"}}',
    )
    get_settings.cache_clear()

    captured_request: dict[str, object] = {}

    class _FakeEmrClient:
        def start_job_run(self, **kwargs):
            captured_request.update(kwargs)
            return {
                "id": "jr-1234567890ab",
                "ResponseMetadata": {"RequestId": "req-123"},
            }

    class _FakeSession:
        def client(self, service_name, region_name=None):
            assert service_name == "emr-containers"
            assert region_name == "us-east-1"
            return _FakeEmrClient()

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", lambda *_args, **_kwargs: _FakeSession())

    environment = SimpleNamespace(
        id="env-123",
        emr_virtual_cluster_id="vc-123",
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
        tenant_id="tenant-123",
        eks_namespace="sparkpilot-team-a",
    )
    job = SimpleNamespace(
        id="job-123",
        name="demo-job",
        artifact_uri="s3://bucket/jobs/demo.py",
        args_json=["s3://bucket/input/events.json"],
        spark_conf_json={},
        retry_max_attempts=1,
    )
    run = SimpleNamespace(
        id="run-123",
        attempt=1,
        args_overrides_json=[],
        spark_conf_overrides_json={},
    )

    result = EmrEksClient().start_job_run(environment, job, run)
    assert result.emr_job_run_id == "jr-1234567890ab"

    spark_driver = captured_request["jobDriver"]["sparkSubmitJobDriver"]
    assert spark_driver["entryPoint"] == "s3://bucket/jobs/demo.py"
    assert spark_driver["entryPointArguments"] == ["s3://bucket/input/events.json"]
    parameters = spark_driver["sparkSubmitParameters"]
    assert "--conf spark.kubernetes.driver.label.sparkpilot-team=tenant-123" in parameters
    assert "--conf spark.kubernetes.executor.label.sparkpilot-team=tenant-123" in parameters
    assert "--conf spark.kubernetes.driver.label.sparkpilot-project=sparkpilot-team-a" in parameters
    assert "--conf spark.kubernetes.executor.label.sparkpilot-project=sparkpilot-team-a" in parameters
    assert "--conf spark.kubernetes.driver.label.sparkpilot-cost-center=cc-analytics" in parameters
    assert "--conf spark.kubernetes.executor.label.sparkpilot-cost-center=cc-analytics" in parameters
    run_name = str(captured_request["name"])
    assert len(run_name) <= 64
    assert run_name.endswith("run-123")
    assert captured_request["tags"]["sparkpilot:run_id"] == "run-123"
    assert captured_request["tags"]["sparkpilot:team"] == "tenant-123"
    assert captured_request["tags"]["sparkpilot:project"] == "sparkpilot-team-a"
    assert captured_request["tags"]["sparkpilot:cost_center"] == "cc-analytics"

    get_settings.cache_clear()


def test_emr_job_run_name_is_length_safe_and_sanitized() -> None:
    name = _emr_job_run_name(
        "live matrix job with spaces and symbols !!! " + ("x" * 100),
        "aba75407-9a39-4212-be08-fcfd180aeeeb",
    )
    assert len(name) <= 64
    assert name.endswith("fcfd180aeeeb")
    assert " " not in name
    assert "!" not in name


def test_check_execution_role_trust_policy_missing_statement_is_actionable(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv(
        "SPARKPILOT_EMR_EXECUTION_ROLE_ARN",
        "arn:aws:iam::123456789012:role/SparkPilotEmrExecutionRole",
    )
    get_settings.cache_clear()

    class _FakeEksClient:
        def describe_cluster(self, **kwargs):
            assert kwargs["name"] == "customer-shared"
            return {
                "cluster": {
                    "identity": {
                        "oidc": {
                            "issuer": "https://oidc.eks.us-east-1.amazonaws.com/id/ABC123",
                        }
                    }
                }
            }

    class _FakeIamClient:
        def get_role(self, **kwargs):
            assert kwargs["RoleName"] == "SparkPilotEmrExecutionRole"
            return {
                "Role": {
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [],
                    }
                }
            }

    class _FakeSession:
        def client(self, service_name, region_name=None):
            if service_name == "eks":
                assert region_name == "us-east-1"
                return _FakeEksClient()
            if service_name == "iam":
                return _FakeIamClient()
            raise AssertionError(f"Unexpected service: {service_name}")

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", lambda *_args, **_kwargs: _FakeSession())

    environment = SimpleNamespace(
        eks_cluster_arn="arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
        eks_namespace="sparkpilot-team",
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
    )

    with pytest.raises(ValueError) as exc_info:
        EmrEksClient().check_execution_role_trust_policy(environment)
    message = str(exc_info.value)
    assert "missing required EMR on EKS web-identity statement" in message
    assert "update-role-trust-policy" in message
    get_settings.cache_clear()


def test_check_customer_role_dispatch_permissions_detects_denies(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv(
        "SPARKPILOT_EMR_EXECUTION_ROLE_ARN",
        "arn:aws:iam::123456789012:role/SparkPilotEmrExecutionRole",
    )
    get_settings.cache_clear()

    class _FakeIamClient:
        def simulate_principal_policy(self, **kwargs):
            if kwargs["ActionNames"] == ["iam:PassRole"]:
                return {
                    "EvaluationResults": [
                        {"EvalActionName": "iam:PassRole", "EvalDecision": "implicitDeny"},
                    ]
                }
            return {
                "EvaluationResults": [
                    {"EvalActionName": "emr-containers:StartJobRun", "EvalDecision": "allowed"},
                    {"EvalActionName": "emr-containers:DescribeJobRun", "EvalDecision": "implicitDeny"},
                    {"EvalActionName": "emr-containers:CancelJobRun", "EvalDecision": "allowed"},
                ]
            }

    class _FakeSession:
        def client(self, service_name, region_name=None):
            assert service_name == "iam"
            return _FakeIamClient()

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", lambda *_args, **_kwargs: _FakeSession())

    environment = SimpleNamespace(
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
    )
    result = EmrEksClient().check_customer_role_dispatch_permissions(environment)
    assert result["dispatch_actions_allowed"] is False
    assert result["pass_role_allowed"] is False
    assert "emr-containers:DescribeJobRun" in (result["denied_dispatch_actions"] or "")
    get_settings.cache_clear()


def test_validate_virtual_cluster_reference_success(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    get_settings.cache_clear()

    class _FakeEmrContainersClient:
        def describe_virtual_cluster(self, **kwargs):
            assert kwargs["id"] == "vc-abc123"
            return {
                "virtualCluster": {
                    "state": "RUNNING",
                    "containerProvider": {
                        "id": "customer-shared",
                        "type": "EKS",
                        "info": {"eksInfo": {"namespace": "sparkpilot-team"}},
                    },
                }
            }

    class _FakeSession:
        def client(self, service_name, region_name=None):
            assert service_name == "emr-containers"
            assert region_name == "us-east-1"
            return _FakeEmrContainersClient()

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", lambda *_args, **_kwargs: _FakeSession())

    environment = SimpleNamespace(
        eks_cluster_arn="arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
        eks_namespace=None,
        emr_virtual_cluster_id="vc-abc123",
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
    )
    result = EmrEksClient().validate_virtual_cluster_reference(environment, require_running=True)
    assert result["valid"] is True
    assert result["state"] == "RUNNING"
    assert result["cluster_name"] == "customer-shared"
    assert result["namespace"] == "sparkpilot-team"
    get_settings.cache_clear()


def test_validate_virtual_cluster_reference_requires_running_state(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    get_settings.cache_clear()

    class _FakeEmrContainersClient:
        def describe_virtual_cluster(self, **kwargs):
            return {
                "virtualCluster": {
                    "state": "TERMINATED",
                    "containerProvider": {
                        "id": "customer-shared",
                        "type": "EKS",
                        "info": {"eksInfo": {"namespace": "sparkpilot-team"}},
                    },
                }
            }

    class _FakeSession:
        def client(self, service_name, region_name=None):
            assert service_name == "emr-containers"
            assert region_name == "us-east-1"
            return _FakeEmrContainersClient()

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", lambda *_args, **_kwargs: _FakeSession())

    environment = SimpleNamespace(
        eks_cluster_arn="arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
        eks_namespace="sparkpilot-team",
        emr_virtual_cluster_id="vc-abc123",
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
    )
    with pytest.raises(ValueError) as exc_info:
        EmrEksClient().validate_virtual_cluster_reference(environment, require_running=True)
    message = str(exc_info.value)
    assert "vc-abc123" in message
    assert "RUNNING" in message
    assert "provisioning_emr" in message
    get_settings.cache_clear()


def test_validate_virtual_cluster_reference_resource_not_found_is_actionable(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    get_settings.cache_clear()

    class _FakeEmrContainersClient:
        def describe_virtual_cluster(self, **_kwargs):
            raise ClientError(
                {
                    "Error": {
                        "Code": "ResourceNotFoundException",
                        "Message": "Virtual cluster not found",
                    }
                },
                "DescribeVirtualCluster",
            )

    class _FakeSession:
        def client(self, service_name, region_name=None):
            assert service_name == "emr-containers"
            assert region_name == "us-east-1"
            return _FakeEmrContainersClient()

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", lambda *_args, **_kwargs: _FakeSession())

    environment = SimpleNamespace(
        eks_cluster_arn="arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
        eks_namespace="sparkpilot-team",
        emr_virtual_cluster_id="vc-missing",
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
    )
    with pytest.raises(ValueError) as exc_info:
        EmrEksClient().validate_virtual_cluster_reference(environment, require_running=False)
    message = str(exc_info.value)
    assert "vc-missing" in message
    assert "not found" in message.lower()
    assert "provisioning_emr" in message
    get_settings.cache_clear()


def test_validate_virtual_cluster_reference_access_denied_is_actionable(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    get_settings.cache_clear()

    class _FakeEmrContainersClient:
        def describe_virtual_cluster(self, **_kwargs):
            raise ClientError(
                {
                    "Error": {
                        "Code": "AccessDeniedException",
                        "Message": "User is not authorized to perform emr-containers:DescribeVirtualCluster",
                    }
                },
                "DescribeVirtualCluster",
            )

    class _FakeSession:
        def client(self, service_name, region_name=None):
            assert service_name == "emr-containers"
            assert region_name == "us-east-1"
            return _FakeEmrContainersClient()

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", lambda *_args, **_kwargs: _FakeSession())

    environment = SimpleNamespace(
        eks_cluster_arn="arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
        eks_namespace="sparkpilot-team",
        emr_virtual_cluster_id="vc-access-denied",
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
    )
    with pytest.raises(ValueError) as exc_info:
        EmrEksClient().validate_virtual_cluster_reference(environment, require_running=False)
    message = str(exc_info.value)
    assert "Access denied while validating EMR virtual cluster reference." in message
    assert "emr-containers:DescribeVirtualCluster" in message
    assert "eks:DescribeCluster" in message
    get_settings.cache_clear()


def test_describe_nodegroups_returns_capacity_metadata(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    get_settings.cache_clear()

    class _FakeEksClient:
        def list_nodegroups(self, **kwargs):
            assert kwargs["clusterName"] == "customer-shared"
            return {"nodegroups": ["spot-ng", "od-ng"]}

        def describe_nodegroup(self, **kwargs):
            if kwargs["nodegroupName"] == "spot-ng":
                return {
                    "nodegroup": {
                        "capacityType": "SPOT",
                        "instanceTypes": ["m7g.xlarge", "m7i.xlarge", "r7g.xlarge"],
                        "scalingConfig": {"desiredSize": 3},
                    }
                }
            return {
                "nodegroup": {
                    "capacityType": "ON_DEMAND",
                    "instanceTypes": ["m7i.large"],
                    "scalingConfig": {"desiredSize": 2},
                }
            }

    class _FakeSession:
        def client(self, service_name, region_name=None):
            assert service_name == "eks"
            assert region_name == "us-east-1"
            return _FakeEksClient()

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", lambda *_args, **_kwargs: _FakeSession())

    environment = SimpleNamespace(
        eks_cluster_arn="arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
    )
    results = EmrEksClient().describe_nodegroups(environment)
    assert len(results) == 2
    assert results[0]["name"] == "spot-ng"
    assert results[0]["capacity_type"] == "SPOT"
    assert results[0]["desired_size"] == 3
    assert "m7g.xlarge" in results[0]["instance_types"]
    get_settings.cache_clear()


def test_describe_nodegroups_access_denied_is_actionable(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    get_settings.cache_clear()

    class _FakeEksClient:
        def list_nodegroups(self, **_kwargs):
            raise ClientError(
                {
                    "Error": {
                        "Code": "AccessDeniedException",
                        "Message": "User is not authorized to perform eks:ListNodegroups",
                    }
                },
                "ListNodegroups",
            )

    class _FakeSession:
        def client(self, service_name, region_name=None):
            assert service_name == "eks"
            assert region_name == "us-east-1"
            return _FakeEksClient()

    monkeypatch.setattr("sparkpilot.aws_clients.assume_role_session", lambda *_args, **_kwargs: _FakeSession())

    environment = SimpleNamespace(
        eks_cluster_arn="arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
    )
    with pytest.raises(ValueError) as exc_info:
        EmrEksClient().describe_nodegroups(environment)
    message = str(exc_info.value)
    assert "eks:ListNodegroups" in message
    assert "eks:DescribeNodegroup" in message
    assert "retry preflight" in message
    get_settings.cache_clear()


def test_list_release_labels_uses_pagination(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    get_settings.cache_clear()

    class _FakeEmrContainersClient:
        def __init__(self):
            self.calls = 0

        def list_release_labels(self, **kwargs):
            self.calls += 1
            if kwargs.get("nextToken") == "t2":
                return {"releaseLabels": ["emr-7.9.0-latest"]}
            return {"releaseLabels": ["emr-7.10.0-latest"], "nextToken": "t2"}

    fake_client = _FakeEmrContainersClient()

    monkeypatch.setattr("sparkpilot.aws_clients.boto3.client", lambda *_args, **_kwargs: fake_client)

    labels = EmrEksClient().list_release_labels("us-east-1")
    assert labels == ["emr-7.10.0-latest", "emr-7.9.0-latest"]
    get_settings.cache_clear()
