from sparkpilot.config import get_settings
from sparkpilot.services.iam_validation import validate_assume_role_chain


def test_validate_assume_role_chain_includes_external_id_from_settings(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.setenv("SPARKPILOT_ASSUME_ROLE_EXTERNAL_ID", "tenant-external-id-123")
    get_settings.cache_clear()

    observed_kwargs: dict[str, object] = {}

    class _FakeStsClient:
        def assume_role(self, **kwargs):
            observed_kwargs.update(kwargs)
            return {
                "AssumedRoleUser": {
                    "Arn": "arn:aws:sts::123456789012:assumed-role/SparkPilotCustomerRole/session",
                },
                "Credentials": {
                    "AccessKeyId": "AKIAEXAMPLE",
                    "SecretAccessKey": "secret",
                    "SessionToken": "token",
                },
            }

        def get_caller_identity(self):
            return {
                "Account": "123456789012",
                "Arn": "arn:aws:sts::123456789012:assumed-role/SparkPilotCustomerRole/session",
            }

    class _FakeAssumedSession:
        def client(self, service_name: str):
            assert service_name == "sts"
            return _FakeStsClient()

    monkeypatch.setattr("sparkpilot.services.iam_validation.boto3.client", lambda *args, **kwargs: _FakeStsClient())
    monkeypatch.setattr("sparkpilot.services.iam_validation.boto3.Session", lambda **kwargs: _FakeAssumedSession())

    result = validate_assume_role_chain(
        "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
    )

    assert result["success"] is True
    assert observed_kwargs["ExternalId"] == "tenant-external-id-123"

    get_settings.cache_clear()


def test_validate_assume_role_chain_omits_external_id_when_unset(monkeypatch) -> None:
    monkeypatch.setenv("SPARKPILOT_DRY_RUN_MODE", "false")
    monkeypatch.delenv("SPARKPILOT_ASSUME_ROLE_EXTERNAL_ID", raising=False)
    monkeypatch.delenv("ASSUME_ROLE_EXTERNAL_ID", raising=False)
    get_settings.cache_clear()

    observed_kwargs: dict[str, object] = {}

    class _FakeStsClient:
        def assume_role(self, **kwargs):
            observed_kwargs.update(kwargs)
            return {
                "AssumedRoleUser": {
                    "Arn": "arn:aws:sts::123456789012:assumed-role/SparkPilotCustomerRole/session",
                },
                "Credentials": {
                    "AccessKeyId": "AKIAEXAMPLE",
                    "SecretAccessKey": "secret",
                    "SessionToken": "token",
                },
            }

        def get_caller_identity(self):
            return {
                "Account": "123456789012",
                "Arn": "arn:aws:sts::123456789012:assumed-role/SparkPilotCustomerRole/session",
            }

    class _FakeAssumedSession:
        def client(self, service_name: str):
            assert service_name == "sts"
            return _FakeStsClient()

    monkeypatch.setattr("sparkpilot.services.iam_validation.boto3.client", lambda *args, **kwargs: _FakeStsClient())
    monkeypatch.setattr("sparkpilot.services.iam_validation.boto3.Session", lambda **kwargs: _FakeAssumedSession())

    result = validate_assume_role_chain(
        "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
        region="us-east-1",
    )

    assert result["success"] is True
    assert "ExternalId" not in observed_kwargs

    get_settings.cache_clear()
