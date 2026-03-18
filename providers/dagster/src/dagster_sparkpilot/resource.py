from __future__ import annotations

from typing import Any

from dagster_sparkpilot._compat import Field, InitResourceContext, resource
from dagster_sparkpilot.client import SparkPilotClient, SparkPilotClientConfig

SPARKPILOT_RESOURCE_CONFIG_SCHEMA = {
    "base_url": Field(
        str,
        description="SparkPilot API base URL (for example http://sparkpilot-api:8000).",
    ),
    "oidc_issuer": Field(
        str,
        description="OIDC issuer URL used for client-credentials discovery.",
    ),
    "oidc_audience": Field(
        str,
        description="OIDC audience expected by SparkPilot API.",
    ),
    "oidc_client_id": Field(
        str,
        description="OIDC client id used for token retrieval.",
    ),
    "oidc_client_secret": Field(
        str,
        description="OIDC client secret used for token retrieval.",
    ),
    "oidc_token_endpoint": Field(
        str,
        is_required=False,
        default_value="",
        description="Explicit token endpoint; when omitted, issuer discovery is used.",
    ),
    "oidc_scope": Field(
        str,
        is_required=False,
        default_value="",
        description="Optional OAuth scope passed during token retrieval.",
    ),
    "timeout_seconds": Field(
        float,
        is_required=False,
        default_value=30.0,
        description="HTTP timeout for SparkPilot API and OIDC calls.",
    ),
    "request_retries": Field(
        int,
        is_required=False,
        default_value=2,
        description="Retry count for transient transport/status errors.",
    ),
    "request_backoff_seconds": Field(
        float,
        is_required=False,
        default_value=1.0,
        description="Linear retry backoff multiplier in seconds.",
    ),
}


class SparkPilotResource:
    """Dagster resource wrapper that lazily initializes a SparkPilotClient."""

    def __init__(self, config: SparkPilotClientConfig) -> None:
        self.config = config
        self._client: SparkPilotClient | None = None

    def get_client(self) -> SparkPilotClient:
        if self._client is None:
            self._client = SparkPilotClient(self.config)
        return self._client


def sparkpilot_resource_from_config(config: dict[str, Any]) -> SparkPilotResource:
    normalized_config = dict(config)
    normalized_config["oidc_token_endpoint"] = normalized_config.get("oidc_token_endpoint") or None
    normalized_config["oidc_scope"] = normalized_config.get("oidc_scope") or None
    client_config = SparkPilotClientConfig.from_mapping(normalized_config)
    return SparkPilotResource(client_config)


@resource(config_schema=SPARKPILOT_RESOURCE_CONFIG_SCHEMA)
def sparkpilot_resource(init_context: InitResourceContext) -> SparkPilotResource:
    return sparkpilot_resource_from_config(getattr(init_context, "resource_config", {}))

