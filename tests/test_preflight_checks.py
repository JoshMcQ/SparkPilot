from types import SimpleNamespace

import sparkpilot.services.preflight_checks as preflight_checks


def _env() -> SimpleNamespace:
    return SimpleNamespace(
        engine="emr_on_eks",
        provisioning_mode="byoc_lite",
        customer_role_arn="arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
        eks_cluster_arn="arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
        eks_namespace="sparkpilot-team",
    )


def _collector() -> tuple[list[dict[str, object]], callable]:
    checks: list[dict[str, object]] = []

    def add_check(*, code: str, status_value: str, message: str, remediation: str | None = None, details=None):
        checks.append(
            {
                "code": code,
                "status": status_value,
                "message": message,
                "remediation": remediation,
                "details": details or {},
            }
        )

    return checks, add_check


def test_issue3_dispatch_gate_short_circuits_when_sts_fails(monkeypatch) -> None:
    env = _env()
    checks, add_check = _collector()

    monkeypatch.setattr(
        preflight_checks,
        "validate_assume_role_chain",
        lambda *_args, **_kwargs: {
            "success": False,
            "error": "Access denied assuming customer role.",
            "remediation": "Fix trust policy.",
        },
    )

    preflight_checks._add_issue3_dispatch_gate_checks(environment=env, add_check=add_check)

    assert [item["code"] for item in checks] == [
        "issue3.sts_caller_identity",
        "issue3.iam_simulate_principal_policy",
        "issue3.eks_describe_cluster",
        "issue3.irsa_trust_subject",
    ]
    assert checks[0]["status"] == "fail"
    assert checks[1]["status"] == "warning"
    assert checks[2]["status"] == "warning"
    assert checks[3]["status"] == "warning"


class _FakeIamClient:
    def simulate_principal_policy(self, **kwargs):
        action_names = kwargs.get("ActionNames", [])
        if action_names == ["iam:PassRole"]:
            return {
                "EvaluationResults": [
                    {
                        "EvalActionName": "iam:PassRole",
                        "EvalDecision": "explicitDeny",
                    }
                ]
            }
        return {
            "EvaluationResults": [
                {
                    "EvalActionName": "emr-containers:StartJobRun",
                    "EvalDecision": "explicitDeny",
                },
                {
                    "EvalActionName": "emr-containers:DescribeJobRun",
                    "EvalDecision": "allowed",
                },
                {
                    "EvalActionName": "emr-containers:CancelJobRun",
                    "EvalDecision": "allowed",
                },
                {
                    "EvalActionName": "eks:DescribeCluster",
                    "EvalDecision": "allowed",
                },
            ]
        }


class _FakeEksClientMissingOidc:
    def describe_cluster(self, *, name: str):
        return {
            "cluster": {
                "name": name,
                "status": "ACTIVE",
                "arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
                "identity": {"oidc": {}},
            }
        }


class _FakeSession:
    def __init__(self, *, iam_client=None, eks_client=None):
        self._iam_client = iam_client
        self._eks_client = eks_client

    def client(self, service_name: str, **_kwargs):
        if service_name == "iam":
            return self._iam_client
        if service_name == "eks":
            return self._eks_client
        raise AssertionError(f"Unexpected service client request: {service_name}")


def test_issue3_iam_simulation_reports_denied_actions(monkeypatch) -> None:
    env = _env()
    checks, add_check = _collector()

    monkeypatch.setattr(
        preflight_checks,
        "get_settings",
        lambda: SimpleNamespace(
            dry_run_mode=False,
            emr_execution_role_arn="arn:aws:iam::123456789012:role/SparkPilotEmrExecutionRole",
        ),
    )
    monkeypatch.setattr(
        preflight_checks,
        "assume_role_session",
        lambda *_args, **_kwargs: _FakeSession(iam_client=_FakeIamClient()),
    )

    ready = preflight_checks._add_issue3_iam_simulation_check(environment=env, add_check=add_check)

    assert ready is False
    assert len(checks) == 1
    assert checks[0]["code"] == "issue3.iam_simulate_principal_policy"
    assert checks[0]["status"] == "fail"
    denied_actions = str(checks[0]["details"].get("denied_actions", ""))
    assert "emr-containers:StartJobRun" in denied_actions
    assert "iam:PassRole" in denied_actions


def test_issue3_eks_describe_cluster_fails_when_oidc_issuer_missing(monkeypatch) -> None:
    env = _env()
    checks, add_check = _collector()

    class _FakeEmrEksClient:
        @staticmethod
        def _eks_cluster_name_from_arn(_arn: str) -> str:
            return "customer-shared"

    monkeypatch.setattr(
        preflight_checks,
        "get_settings",
        lambda: SimpleNamespace(dry_run_mode=False),
    )
    monkeypatch.setattr(preflight_checks, "EmrEksClient", _FakeEmrEksClient)
    monkeypatch.setattr(
        preflight_checks,
        "assume_role_session",
        lambda *_args, **_kwargs: _FakeSession(eks_client=_FakeEksClientMissingOidc()),
    )

    ready = preflight_checks._add_issue3_eks_describe_cluster_check(environment=env, add_check=add_check)

    assert ready is False
    assert len(checks) == 1
    assert checks[0]["code"] == "issue3.eks_describe_cluster"
    assert checks[0]["status"] == "fail"
    remediation = str(checks[0]["remediation"] or "")
    assert "associate-iam-oidc-provider" in remediation


def test_issue3_dispatch_gate_adds_all_pass_checks_with_mocked_aws(monkeypatch) -> None:
    env = _env()
    checks, add_check = _collector()

    class _FakeEmrEksClient:
        @staticmethod
        def _eks_cluster_name_from_arn(_arn: str) -> str:
            return "customer-shared"

        @staticmethod
        def check_execution_role_trust_policy(_environment):
            return {
                "provider_arn": "arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/abcd",
                "service_account_pattern": "system:serviceaccount:sparkpilot-team:emr-containers-sa-*-*-123456789012-SparkPilotEmrExecutionRole",
                "role_name": "SparkPilotEmrExecutionRole",
            }

    class _FakeIamAllAllowed:
        def simulate_principal_policy(self, **kwargs):
            action_names = kwargs.get("ActionNames", [])
            if action_names == ["iam:PassRole"]:
                return {
                    "EvaluationResults": [
                        {
                            "EvalActionName": "iam:PassRole",
                            "EvalDecision": "allowed",
                        }
                    ]
                }
            return {
                "EvaluationResults": [
                    {
                        "EvalActionName": action,
                        "EvalDecision": "allowed",
                    }
                    for action in action_names
                ]
            }

    class _FakeEksActive:
        def describe_cluster(self, *, name: str):
            return {
                "cluster": {
                    "name": name,
                    "status": "ACTIVE",
                    "arn": "arn:aws:eks:us-east-1:123456789012:cluster/customer-shared",
                    "identity": {
                        "oidc": {
                            "issuer": "https://oidc.eks.us-east-1.amazonaws.com/id/abcd"
                        }
                    },
                }
            }

    monkeypatch.setattr(
        preflight_checks,
        "validate_assume_role_chain",
        lambda *_args, **_kwargs: {
            "success": True,
            "assumed_identity_arn": "arn:aws:sts::123456789012:assumed-role/SparkPilotCustomerRole/session",
            "assumed_account": "123456789012",
        },
    )
    monkeypatch.setattr(
        preflight_checks,
        "get_settings",
        lambda: SimpleNamespace(
            dry_run_mode=False,
            emr_execution_role_arn="arn:aws:iam::123456789012:role/SparkPilotEmrExecutionRole",
        ),
    )
    monkeypatch.setattr(preflight_checks, "EmrEksClient", _FakeEmrEksClient)
    monkeypatch.setattr(
        preflight_checks,
        "assume_role_session",
        lambda *_args, **_kwargs: _FakeSession(
            iam_client=_FakeIamAllAllowed(),
            eks_client=_FakeEksActive(),
        ),
    )

    preflight_checks._add_issue3_dispatch_gate_checks(environment=env, add_check=add_check)

    assert [item["code"] for item in checks] == [
        "issue3.sts_caller_identity",
        "issue3.iam_simulate_principal_policy",
        "issue3.eks_describe_cluster",
        "issue3.irsa_trust_subject",
    ]
    assert all(item["status"] == "pass" for item in checks)
