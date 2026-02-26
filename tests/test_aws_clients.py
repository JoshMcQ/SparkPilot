from botocore.exceptions import ClientError
import pytest

from sparkpilot.aws_clients import CloudWatchLogsProxy
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
