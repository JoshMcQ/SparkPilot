from functools import lru_cache
import re
from typing import Literal
from urllib.parse import urlparse
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from sparkpilot.cost_center import parse_cost_center_policy


EMR_EXECUTION_ROLE_PLACEHOLDER_ARN = "arn:aws:iam::111111111111:role/SparkPilotEmrExecutionRole"
IAM_ROLE_ARN_PATTERN = re.compile(r"^arn:aws:iam::\d{12}:role/.+")
MIN_BOOTSTRAP_SECRET_LENGTH = 16


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPARKPILOT_", case_sensitive=False)

    app_name: str = "SparkPilot API"
    environment: str = "dev"
    database_url: str = "postgresql+psycopg://sparkpilot:sparkpilot@localhost:5432/sparkpilot"
    dry_run_mode: bool = False
    enable_full_byoc_mode: bool = False
    auth_mode: Literal["oidc"] = Field(
        default="oidc",
        validation_alias=AliasChoices("SPARKPILOT_AUTH_MODE", "AUTH_MODE"),
    )
    oidc_issuer: str = Field(
        default="",
        validation_alias=AliasChoices("SPARKPILOT_OIDC_ISSUER", "OIDC_ISSUER"),
    )
    oidc_audience: str = Field(
        default="",
        validation_alias=AliasChoices("SPARKPILOT_OIDC_AUDIENCE", "OIDC_AUDIENCE"),
    )
    oidc_jwks_uri: str = Field(
        default="",
        validation_alias=AliasChoices("SPARKPILOT_OIDC_JWKS_URI", "OIDC_JWKS_URI"),
    )
    bootstrap_secret: str = Field(
        default="",
        validation_alias=AliasChoices("SPARKPILOT_BOOTSTRAP_SECRET", "BOOTSTRAP_SECRET"),
    )
    aws_region: str = "us-east-1"
    log_group_prefix: str = "/sparkpilot/runs"
    emr_release_label: str = "emr-7.10.0-latest"
    emr_execution_role_arn: str = ""
    assume_role_external_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_ASSUME_ROLE_EXTERNAL_ID",
            "ASSUME_ROLE_EXTERNAL_ID",
        ),
    )
    queue_batch_size: int = 20
    poll_interval_seconds: int = 15
    accepted_stale_minutes: int = 15
    submitted_stale_minutes: int = 30
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    ops_s3_bucket: str = "sparkpilot-ops"
    cur_athena_database: str = ""
    cur_athena_table: str = ""
    cur_athena_workgroup: str = "primary"
    cur_athena_output_location: str = ""
    cur_run_id_column: str = "resource_tags_user_sparkpilot_run_id"
    cur_cost_column: str = "line_item_unblended_cost"
    cost_center_policy_json: str = ""
    cur_poll_seconds: int = 2
    cur_query_timeout_seconds: int = 120
    pricing_source: Literal["auto", "static", "aws_pricing_api"] = "auto"
    pricing_cache_seconds: int = 21600
    pricing_vcpu_usd_per_second: float = 0.000011244
    pricing_memory_gb_usd_per_second: float = 0.000001235
    pricing_arm64_discount_pct: float = 20.0
    pricing_mixed_discount_pct: float = 10.0
    databricks_token: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [item.strip() for item in self.cors_origins.split(",")]
        return [item for item in origins if item]


def is_valid_iam_role_arn(value: str) -> bool:
    return bool(IAM_ROLE_ARN_PATTERN.match(value.strip()))


_DEFAULT_DATABASE_URL = "postgresql+psycopg://sparkpilot:sparkpilot@localhost:5432/sparkpilot"
_LOCALHOST_ORIGINS = {"localhost", "127.0.0.1", "::1"}


def _validate_environment_mode(settings: Settings) -> bool:
    environment_name = settings.environment.strip().lower()
    is_dev_like_environment = environment_name in {"dev", "development", "local", "test"}
    if settings.database_url.startswith("sqlite") and not is_dev_like_environment:
        raise ValueError(
            "SQLite is only supported in development/test environments. "
            "Use PostgreSQL for staging/production deployments."
        )
    if settings.dry_run_mode and not is_dev_like_environment:
        raise ValueError(
            "SPARKPILOT_DRY_RUN_MODE=true is only allowed in development/test environments."
        )
    if not is_dev_like_environment:
        if settings.database_url == _DEFAULT_DATABASE_URL:
            raise ValueError(
                "SPARKPILOT_DATABASE_URL must be explicitly set in non-development environments. "
                "The default localhost URL must not be used in staging or production."
            )
        localhost_cors = [
            o for o in settings.cors_origin_list
            if urlparse(o).hostname in _LOCALHOST_ORIGINS
        ]
        if localhost_cors:
            raise ValueError(
                f"SPARKPILOT_CORS_ORIGINS contains localhost origins {localhost_cors} "
                "which are not allowed in non-development environments."
            )
    return is_dev_like_environment


def _validate_numeric_runtime_settings(settings: Settings) -> None:
    if settings.accepted_stale_minutes <= 0:
        raise ValueError("SPARKPILOT_ACCEPTED_STALE_MINUTES must be greater than 0.")
    if settings.submitted_stale_minutes <= 0:
        raise ValueError("SPARKPILOT_SUBMITTED_STALE_MINUTES must be greater than 0.")
    if settings.pricing_cache_seconds <= 0:
        raise ValueError("SPARKPILOT_PRICING_CACHE_SECONDS must be greater than 0.")
    if settings.pricing_vcpu_usd_per_second <= 0:
        raise ValueError("SPARKPILOT_PRICING_VCPU_USD_PER_SECOND must be greater than 0.")
    if settings.pricing_memory_gb_usd_per_second <= 0:
        raise ValueError("SPARKPILOT_PRICING_MEMORY_GB_USD_PER_SECOND must be greater than 0.")
    if not (0 <= settings.pricing_arm64_discount_pct <= 100):
        raise ValueError("SPARKPILOT_PRICING_ARM64_DISCOUNT_PCT must be between 0 and 100.")
    if not (0 <= settings.pricing_mixed_discount_pct <= 100):
        raise ValueError("SPARKPILOT_PRICING_MIXED_DISCOUNT_PCT must be between 0 and 100.")



def _validate_auth_settings(settings: Settings) -> None:
    if settings.auth_mode != "oidc":
        raise ValueError("AUTH_MODE must be 'oidc'. No legacy auth modes are supported.")
    issuer = settings.oidc_issuer.strip()
    if not issuer:
        raise ValueError("OIDC_ISSUER is required.")
    parsed_issuer = urlparse(issuer)
    if parsed_issuer.scheme not in {"http", "https"} or not parsed_issuer.netloc:
        raise ValueError("OIDC_ISSUER must be a valid http(s) URL.")
    if not settings.oidc_audience.strip():
        raise ValueError("OIDC_AUDIENCE is required.")
    jwks_uri = settings.oidc_jwks_uri.strip()
    if not jwks_uri:
        raise ValueError("OIDC_JWKS_URI is required.")
    parsed_jwks = urlparse(jwks_uri)
    if parsed_jwks.scheme == "file":
        if not parsed_jwks.path:
            raise ValueError("OIDC_JWKS_URI file:// URL must include a file path.")
    elif parsed_jwks.scheme not in {"http", "https"} or not parsed_jwks.netloc:
        raise ValueError("OIDC_JWKS_URI must be a valid http(s) or file:// URL.")


def _validate_security_runtime_settings(settings: Settings) -> None:
    bootstrap_secret = settings.bootstrap_secret.strip()
    if len(bootstrap_secret) < MIN_BOOTSTRAP_SECRET_LENGTH:
        raise ValueError(
            f"BOOTSTRAP_SECRET must be set and at least {MIN_BOOTSTRAP_SECRET_LENGTH} characters."
        )
    if not settings.cors_origin_list:
        raise ValueError("SPARKPILOT_CORS_ORIGINS must contain at least one origin.")
    for origin in settings.cors_origin_list:
        if "*" in origin:
            raise ValueError(
                "SPARKPILOT_CORS_ORIGINS cannot contain wildcard origins when credentialed CORS is enabled."
            )
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                "SPARKPILOT_CORS_ORIGINS must contain valid http(s) origins in scheme://host[:port] format."
            )


def _validate_cost_center_policy(settings: Settings) -> None:
    if settings.cost_center_policy_json.strip():
        try:
            parse_cost_center_policy(settings.cost_center_policy_json)
        except ValueError as exc:
            raise ValueError(f"SPARKPILOT_COST_CENTER_POLICY_JSON is invalid: {exc}") from exc


def _validate_live_mode_role_arn(settings: Settings) -> None:
    role_arn = settings.emr_execution_role_arn.strip()
    if not role_arn:
        raise ValueError(
            "SPARKPILOT_EMR_EXECUTION_ROLE_ARN is required when SPARKPILOT_DRY_RUN_MODE=false."
        )
    if role_arn == EMR_EXECUTION_ROLE_PLACEHOLDER_ARN:
        raise ValueError(
            "SPARKPILOT_EMR_EXECUTION_ROLE_ARN is using the placeholder execution role ARN. "
            "Set a real role ARN before starting SparkPilot in live mode."
        )
    if not is_valid_iam_role_arn(role_arn):
        raise ValueError(
            "SPARKPILOT_EMR_EXECUTION_ROLE_ARN must be a valid IAM role ARN "
            "(arn:aws:iam::<12-digit-account-id>:role/<role-name>)."
        )


def validate_runtime_settings(settings: Settings) -> None:
    _validate_environment_mode(settings)
    _validate_numeric_runtime_settings(settings)
    _validate_cost_center_policy(settings)
    _validate_auth_settings(settings)
    _validate_security_runtime_settings(settings)
    if settings.dry_run_mode:
        return
    _validate_live_mode_role_arn(settings)


@lru_cache
def get_settings() -> Settings:
    return Settings()
