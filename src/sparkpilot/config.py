from functools import lru_cache
import hashlib
import logging
import re
from typing import Literal, cast
from urllib.parse import urlparse
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from sparkpilot.cost_center import parse_cost_center_policy


EMR_EXECUTION_ROLE_PLACEHOLDER_ARN = (
    "arn:aws:iam::111111111111:role/SparkPilotEmrExecutionRole"
)
IAM_ROLE_ARN_PATTERN = re.compile(r"^arn:aws:iam::\d{12}:role/.+")
MIN_BOOTSTRAP_SECRET_LENGTH = 16
MIN_CONTACT_SUBMIT_TOKEN_LENGTH = 32
_DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://sparkpilot:sparkpilot@localhost:5432/sparkpilot"
)
_LOCALHOST_ORIGINS = {"localhost", "127.0.0.1", "::1"}
EMAIL_ADDRESS_PATTERN = re.compile(r"^[^<>@\s]+@[^<>@\s]+\.[^<>@\s]+$")
FRIENDLY_EMAIL_ADDRESS_PATTERN = re.compile(
    r"^.+<(?P<email>[^<>@\s]+@[^<>@\s]+\.[^<>@\s]+)>$"
)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPARKPILOT_", case_sensitive=False)

    app_name: str = "SparkPilot API"
    app_base_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_APP_BASE_URL",
            "APP_BASE_URL",
            "SPARKPILOT_UI_APP_BASE_URL",
            "UI_APP_BASE_URL",
        ),
    )
    environment: str = "dev"
    database_url: str = _DEFAULT_DATABASE_URL
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
    customer_oidc_issuer: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_CUSTOMER_OIDC_ISSUER", "CUSTOMER_OIDC_ISSUER"
        ),
    )
    customer_oidc_audience: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_CUSTOMER_OIDC_AUDIENCE", "CUSTOMER_OIDC_AUDIENCE"
        ),
    )
    customer_oidc_jwks_uri: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_CUSTOMER_OIDC_JWKS_URI", "CUSTOMER_OIDC_JWKS_URI"
        ),
    )
    internal_oidc_issuer: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_INTERNAL_OIDC_ISSUER", "INTERNAL_OIDC_ISSUER"
        ),
    )
    internal_oidc_audience: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_INTERNAL_OIDC_AUDIENCE", "INTERNAL_OIDC_AUDIENCE"
        ),
    )
    internal_oidc_jwks_uri: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_INTERNAL_OIDC_JWKS_URI", "INTERNAL_OIDC_JWKS_URI"
        ),
    )
    bootstrap_secret: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_BOOTSTRAP_SECRET", "BOOTSTRAP_SECRET"
        ),
    )
    invite_state_secret: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_INVITE_STATE_SECRET", "INVITE_STATE_SECRET"
        ),
    )
    bootstrap_flow: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_BOOTSTRAP_FLOW",
            "BOOTSTRAP_FLOW",
        ),
    )
    internal_admins: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_INTERNAL_ADMINS",
            "INTERNAL_ADMINS",
        ),
    )
    cognito_hosted_ui_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_COGNITO_HOSTED_UI_URL",
            "COGNITO_HOSTED_UI_URL",
        ),
    )
    crm_webhook_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_CRM_WEBHOOK_URL",
            "CRM_WEBHOOK_URL",
        ),
    )
    resend_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("SPARKPILOT_RESEND_API_KEY", "RESEND_API_KEY"),
    )
    invite_email_from: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_INVITE_EMAIL_FROM",
            "INVITE_EMAIL_FROM",
        ),
    )
    invite_email_reply_to: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_INVITE_EMAIL_REPLY_TO",
            "INVITE_EMAIL_REPLY_TO",
        ),
    )
    contact_email_recipient: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_CONTACT_EMAIL_RECIPIENT",
            "CONTACT_EMAIL_RECIPIENT",
        ),
    )
    contact_submit_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SPARKPILOT_CONTACT_SUBMIT_TOKEN",
            "CONTACT_SUBMIT_TOKEN",
        ),
    )
    contact_submit_duplicate_window_seconds: int = Field(default=1800, ge=1, le=86400)
    contact_submit_rate_limit_max: int = Field(default=5, ge=1, le=1000)
    contact_submit_rate_limit_window_seconds: int = Field(default=300, ge=1, le=86400)
    invite_email_timeout_seconds: float = 10.0
    magic_link_ttl_hours: int = 24
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

    @property
    def bootstrap_flow_mode(self) -> Literal["enabled", "disabled"]:
        raw = self.bootstrap_flow.strip().lower()
        if raw in {"enabled", "disabled"}:
            return cast(Literal["enabled", "disabled"], raw)
        environment_name = self.environment.strip().lower()
        if environment_name in {"dev", "development", "local", "test"}:
            return "enabled"
        return "disabled"

    @property
    def bootstrap_flow_enabled(self) -> bool:
        return self.bootstrap_flow_mode == "enabled"

    @property
    def internal_admin_email_set(self) -> set[str]:
        return {
            email.strip().lower()
            for email in self.internal_admins.split(",")
            if email.strip()
        }

    @property
    def contact_email_recipient_effective(self) -> str:
        explicit = _extract_email_address(self.contact_email_recipient.strip()).lower()
        if explicit:
            return explicit
        reply_to = _extract_email_address(self.invite_email_reply_to.strip()).lower()
        if reply_to:
            return reply_to
        for email in self.internal_admins.split(","):
            normalized = email.strip().lower()
            if normalized:
                return normalized
        return ""

    @property
    def customer_oidc_issuer_effective(self) -> str:
        return self.customer_oidc_issuer.strip() or self.oidc_issuer.strip()

    @property
    def customer_oidc_audience_effective(self) -> str:
        return self.customer_oidc_audience.strip() or self.oidc_audience.strip()

    @property
    def customer_oidc_jwks_uri_effective(self) -> str:
        return self.customer_oidc_jwks_uri.strip() or self.oidc_jwks_uri.strip()

    @property
    def legacy_customer_oidc_aliases_in_use(self) -> list[str]:
        aliases: list[str] = []
        if not self.customer_oidc_issuer.strip() and self.oidc_issuer.strip():
            aliases.append("SPARKPILOT_OIDC_ISSUER")
        if not self.customer_oidc_audience.strip() and self.oidc_audience.strip():
            aliases.append("SPARKPILOT_OIDC_AUDIENCE")
        if not self.customer_oidc_jwks_uri.strip() and self.oidc_jwks_uri.strip():
            aliases.append("SPARKPILOT_OIDC_JWKS_URI")
        return aliases

    @property
    def internal_oidc_issuer_effective(self) -> str:
        return self.internal_oidc_issuer.strip()

    @property
    def internal_oidc_audience_effective(self) -> str:
        return self.internal_oidc_audience.strip()

    @property
    def internal_oidc_jwks_uri_effective(self) -> str:
        return self.internal_oidc_jwks_uri.strip()

    @property
    def invite_state_signing_secret(self) -> str:
        explicit_secret = self.invite_state_secret.strip()
        if explicit_secret:
            return explicit_secret
        base_secret = self.bootstrap_secret.strip().encode("utf-8")
        # Derive a purpose-bound key to avoid reusing bootstrap secret material.
        return hashlib.blake2b(
            base_secret,
            digest_size=32,
            person=b"sp_invite_state",
        ).hexdigest()


def is_valid_iam_role_arn(value: str) -> bool:
    return bool(IAM_ROLE_ARN_PATTERN.match(value.strip()))


def _validate_environment_mode(settings: Settings) -> bool:
    environment_name = settings.environment.strip().lower()
    is_dev_like_environment = environment_name in {
        "dev",
        "development",
        "local",
        "test",
    }
    is_prod_like_environment = environment_name in {"prod", "production"}
    if settings.database_url.startswith("sqlite") and not is_dev_like_environment:
        raise ValueError(
            "SQLite is only supported in development/test environments. "
            "Use PostgreSQL for staging/production deployments."
        )
    if settings.dry_run_mode and is_prod_like_environment:
        raise ValueError(
            "SPARKPILOT_DRY_RUN_MODE=true is not allowed in production environments."
        )
    if not is_dev_like_environment:
        if settings.database_url == _DEFAULT_DATABASE_URL:
            raise ValueError(
                "SPARKPILOT_DATABASE_URL must be explicitly set in non-development environments. "
                "The default localhost URL must not be used in staging or production."
            )
        localhost_cors = [
            o
            for o in settings.cors_origin_list
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
        raise ValueError(
            "SPARKPILOT_PRICING_VCPU_USD_PER_SECOND must be greater than 0."
        )
    if settings.pricing_memory_gb_usd_per_second <= 0:
        raise ValueError(
            "SPARKPILOT_PRICING_MEMORY_GB_USD_PER_SECOND must be greater than 0."
        )
    if not (0 <= settings.pricing_arm64_discount_pct <= 100):
        raise ValueError(
            "SPARKPILOT_PRICING_ARM64_DISCOUNT_PCT must be between 0 and 100."
        )
    if not (0 <= settings.pricing_mixed_discount_pct <= 100):
        raise ValueError(
            "SPARKPILOT_PRICING_MIXED_DISCOUNT_PCT must be between 0 and 100."
        )


def _validate_oidc_triple(*, prefix: str, issuer: str, audience: str, jwks_uri: str) -> None:
    issuer_value = issuer.strip()
    if not issuer_value:
        raise ValueError(f"{prefix}_OIDC_ISSUER is required.")
    parsed_issuer = urlparse(issuer_value)
    if parsed_issuer.scheme not in {"http", "https"} or not parsed_issuer.netloc:
        raise ValueError(f"{prefix}_OIDC_ISSUER must be a valid http(s) URL.")
    if not audience.strip():
        raise ValueError(f"{prefix}_OIDC_AUDIENCE is required.")
    jwks_value = jwks_uri.strip()
    if not jwks_value:
        raise ValueError(f"{prefix}_OIDC_JWKS_URI is required.")
    parsed_jwks = urlparse(jwks_value)
    if parsed_jwks.scheme == "file":
        if not parsed_jwks.path:
            raise ValueError(
                f"{prefix}_OIDC_JWKS_URI file:// URL must include a file path."
            )
    elif parsed_jwks.scheme not in {"http", "https"} or not parsed_jwks.netloc:
        raise ValueError(
            f"{prefix}_OIDC_JWKS_URI must be a valid http(s) or file:// URL."
        )


def _validate_auth_settings(settings: Settings) -> None:
    if settings.auth_mode != "oidc":
        raise ValueError(
            "AUTH_MODE must be 'oidc'. No legacy auth modes are supported."
        )
    _validate_oidc_triple(
        prefix="SPARKPILOT_CUSTOMER",
        issuer=settings.customer_oidc_issuer_effective,
        audience=settings.customer_oidc_audience_effective,
        jwks_uri=settings.customer_oidc_jwks_uri_effective,
    )
    _validate_oidc_triple(
        prefix="SPARKPILOT_INTERNAL",
        issuer=settings.internal_oidc_issuer_effective,
        audience=settings.internal_oidc_audience_effective,
        jwks_uri=settings.internal_oidc_jwks_uri_effective,
    )
    hosted_ui_url = settings.cognito_hosted_ui_url.strip()
    if hosted_ui_url:
        parsed_hosted_ui_url = urlparse(hosted_ui_url)
        if (
            parsed_hosted_ui_url.scheme not in {"http", "https"}
            or not parsed_hosted_ui_url.netloc
        ):
            raise ValueError(
                "SPARKPILOT_COGNITO_HOSTED_UI_URL must be a valid http(s) URL."
            )
    crm_webhook_url = settings.crm_webhook_url.strip()
    if crm_webhook_url:
        parsed_crm_webhook_url = urlparse(crm_webhook_url)
        if (
            parsed_crm_webhook_url.scheme not in {"http", "https"}
            or not parsed_crm_webhook_url.netloc
        ):
            raise ValueError("SPARKPILOT_CRM_WEBHOOK_URL must be a valid http(s) URL.")


def _extract_email_address(value: str) -> str:
    candidate = value.strip()
    if "<" in candidate or ">" in candidate:
        match = FRIENDLY_EMAIL_ADDRESS_PATTERN.fullmatch(candidate)
        if match is None:
            return ""
        candidate = match.group("email")
    return candidate


def _validate_invite_email_settings(settings: Settings) -> None:
    resend_api_key = settings.resend_api_key.strip()
    from_email = settings.invite_email_from.strip()
    reply_to = settings.invite_email_reply_to.strip()
    contact_recipient = settings.contact_email_recipient.strip()
    hosted_ui_url = settings.cognito_hosted_ui_url.strip()
    app_base_url = settings.app_base_url.strip().rstrip("/")
    if app_base_url:
        parsed_app_base_url = urlparse(app_base_url)
        if (
            parsed_app_base_url.scheme not in {"http", "https"}
            or not parsed_app_base_url.netloc
            or parsed_app_base_url.query
            or parsed_app_base_url.fragment
        ):
            raise ValueError(
                "SPARKPILOT_APP_BASE_URL must be a valid http(s) URL without query or fragment."
            )
    if (resend_api_key or from_email) and not hosted_ui_url:
        raise ValueError(
            "SPARKPILOT_COGNITO_HOSTED_UI_URL is required when invite emails are enabled."
        )
    if (resend_api_key or from_email) and not app_base_url:
        raise ValueError(
            "SPARKPILOT_APP_BASE_URL is required when invite emails are enabled."
        )
    if resend_api_key and not from_email:
        raise ValueError(
            "SPARKPILOT_INVITE_EMAIL_FROM is required when SPARKPILOT_RESEND_API_KEY is set."
        )
    if from_email:
        parsed_from = _extract_email_address(from_email)
        if EMAIL_ADDRESS_PATTERN.fullmatch(parsed_from) is None:
            raise ValueError(
                "SPARKPILOT_INVITE_EMAIL_FROM must be an email address or friendly-name address."
            )
    if reply_to:
        parsed_reply_to = _extract_email_address(reply_to)
        if EMAIL_ADDRESS_PATTERN.fullmatch(parsed_reply_to) is None:
            raise ValueError("SPARKPILOT_INVITE_EMAIL_REPLY_TO must be an email address.")
    if contact_recipient:
        parsed_contact_recipient = _extract_email_address(contact_recipient)
        if EMAIL_ADDRESS_PATTERN.fullmatch(parsed_contact_recipient) is None:
            raise ValueError("SPARKPILOT_CONTACT_EMAIL_RECIPIENT must be an email address.")
    if settings.invite_email_timeout_seconds <= 0:
        raise ValueError(
            "SPARKPILOT_INVITE_EMAIL_TIMEOUT_SECONDS must be greater than 0."
        )


def _validate_security_runtime_settings(settings: Settings) -> None:
    bootstrap_secret = settings.bootstrap_secret.strip()
    if len(bootstrap_secret) < MIN_BOOTSTRAP_SECRET_LENGTH:
        raise ValueError(
            f"BOOTSTRAP_SECRET must be set and at least {MIN_BOOTSTRAP_SECRET_LENGTH} characters."
        )
    invite_state_secret = settings.invite_state_secret.strip()
    if invite_state_secret and len(invite_state_secret) < MIN_BOOTSTRAP_SECRET_LENGTH:
        raise ValueError(
            "SPARKPILOT_INVITE_STATE_SECRET must be at least "
            f"{MIN_BOOTSTRAP_SECRET_LENGTH} characters when provided."
        )
    contact_submit_token = settings.contact_submit_token.strip()
    if contact_submit_token and len(contact_submit_token) < MIN_CONTACT_SUBMIT_TOKEN_LENGTH:
        raise ValueError(
            "SPARKPILOT_CONTACT_SUBMIT_TOKEN must be at least "
            f"{MIN_CONTACT_SUBMIT_TOKEN_LENGTH} characters when provided."
        )
    environment = settings.environment.strip().lower()
    if environment not in {"dev", "development", "local", "test"} and not contact_submit_token:
        raise ValueError(
            "SPARKPILOT_CONTACT_SUBMIT_TOKEN must be set outside dev so public contact submissions "
            "can only enter through the app proxy."
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
    if settings.bootstrap_flow.strip():
        normalized = settings.bootstrap_flow.strip().lower()
        if normalized not in {"enabled", "disabled"}:
            raise ValueError(
                "SPARKPILOT_BOOTSTRAP_FLOW must be either 'enabled' or 'disabled'."
            )
    if settings.magic_link_ttl_hours <= 0:
        raise ValueError("SPARKPILOT_MAGIC_LINK_TTL_HOURS must be greater than 0.")


def _validate_cost_center_policy(settings: Settings) -> None:
    if settings.cost_center_policy_json.strip():
        try:
            parse_cost_center_policy(settings.cost_center_policy_json)
        except ValueError as exc:
            raise ValueError(
                f"SPARKPILOT_COST_CENTER_POLICY_JSON is invalid: {exc}"
            ) from exc


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
    _validate_invite_email_settings(settings)
    _validate_security_runtime_settings(settings)
    if settings.legacy_customer_oidc_aliases_in_use:
        logger.warning(
            "Legacy OIDC env aliases in use for customer pool (%s). "
            "Set SPARKPILOT_CUSTOMER_OIDC_* and keep legacy vars only for transition.",
            ",".join(settings.legacy_customer_oidc_aliases_in_use),
        )
    if settings.dry_run_mode:
        return
    _validate_live_mode_role_arn(settings)


@lru_cache
def get_settings() -> Settings:
    return Settings()
