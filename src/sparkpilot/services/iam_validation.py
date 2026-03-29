"""IAM credential chain validation (#76).

Validates the runtime IAM credential chain:
1. Runtime identity (task role / instance role) via sts:GetCallerIdentity
2. Cross-account AssumeRole into customer roles
3. Detects static credential anti-patterns
"""

from __future__ import annotations

import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from sparkpilot.config import get_settings

logger = logging.getLogger(__name__)


def validate_runtime_identity() -> dict[str, Any]:
    """Call sts:GetCallerIdentity to identify the runtime principal.

    Returns a dict with:
    - account: AWS account ID
    - arn: caller ARN
    - user_id: unique identifier
    - is_assumed_role: whether the principal is an assumed role
    - is_instance_role: whether credentials come from instance metadata / task role
    - credential_source: detected source (task_role, instance_profile, static, unknown)
    - valid: whether the identity was resolved
    """
    settings = get_settings()
    if settings.dry_run_mode:
        return {
            "account": "123456789012",
            "arn": "arn:aws:sts::123456789012:assumed-role/SparkPilotTaskRole/session",
            "user_id": "AROAEXAMPLE:session",
            "is_assumed_role": True,
            "is_instance_role": False,
            "credential_source": "task_role",
            "valid": True,
            "mode": "dry_run",
        }

    try:
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        arn = identity.get("Arn", "")
        account = identity.get("Account", "")
        user_id = identity.get("UserId", "")

        is_assumed_role = ":assumed-role/" in arn
        credential_source = _detect_credential_source(arn, user_id)

        return {
            "account": account,
            "arn": arn,
            "user_id": user_id,
            "is_assumed_role": is_assumed_role,
            "is_instance_role": credential_source in ("task_role", "instance_profile"),
            "credential_source": credential_source,
            "valid": True,
        }
    except NoCredentialsError:
        return {
            "account": "",
            "arn": "",
            "user_id": "",
            "is_assumed_role": False,
            "is_instance_role": False,
            "credential_source": "none",
            "valid": False,
            "error": "No AWS credentials found in runtime environment.",
        }
    except ClientError as exc:
        return {
            "account": "",
            "arn": "",
            "user_id": "",
            "is_assumed_role": False,
            "is_instance_role": False,
            "credential_source": "unknown",
            "valid": False,
            "error": str(exc),
        }


def validate_assume_role_chain(
    customer_role_arn: str,
    region: str = "us-east-1",
    external_id: str | None = None,
) -> dict[str, Any]:
    """Validate the AssumeRole chain into a customer role.

    Returns a dict with:
    - assumed_role_arn: the ARN of the assumed role
    - assumed_account: the customer account ID
    - success: whether the assumption succeeded
    - error: error message if failed
    - remediation: suggested fix if failed
    """
    settings = get_settings()
    if settings.dry_run_mode:
        return {
            "assumed_role_arn": customer_role_arn,
            "assumed_account": customer_role_arn.split(":")[4] if ":" in customer_role_arn else "",
            "success": True,
            "mode": "dry_run",
        }

    try:
        sts = boto3.client("sts", region_name=region)
        kwargs: dict[str, Any] = {
            "RoleArn": customer_role_arn,
            "RoleSessionName": "sparkpilot-credential-chain-validation",
            "DurationSeconds": 900,
        }
        resolved_external_id = (external_id or settings.assume_role_external_id).strip()
        if resolved_external_id:
            kwargs["ExternalId"] = resolved_external_id

        response = sts.assume_role(**kwargs)
        assumed_arn = response.get("AssumedRoleUser", {}).get("Arn", "")
        assumed_account = response.get("AssumedRoleUser", {}).get("Arn", "").split(":")[4] if assumed_arn else ""

        # Validate assumed credentials work by calling GetCallerIdentity
        creds = response["Credentials"]
        assumed_session = boto3.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
            region_name=region,
        )
        assumed_identity = assumed_session.client("sts").get_caller_identity()

        return {
            "assumed_role_arn": assumed_arn,
            "assumed_account": assumed_identity.get("Account", assumed_account),
            "assumed_identity_arn": assumed_identity.get("Arn", ""),
            "success": True,
        }
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        message = exc.response.get("Error", {}).get("Message", str(exc))

        if code == "AccessDenied":
            return {
                "assumed_role_arn": "",
                "assumed_account": "",
                "success": False,
                "error": f"Access denied assuming {customer_role_arn}: {message}",
                "remediation": (
                    "Update the customer role trust policy to allow the SparkPilot "
                    "control-plane role to assume it. Check ExternalId constraints."
                ),
            }
        if "is not authorized to perform: sts:AssumeRole" in message:
            return {
                "assumed_role_arn": "",
                "assumed_account": "",
                "success": False,
                "error": message,
                "remediation": (
                    "Grant sts:AssumeRole permission to the SparkPilot runtime role, "
                    "or update the customer role trust policy."
                ),
            }
        return {
            "assumed_role_arn": "",
            "assumed_account": "",
            "success": False,
            "error": f"{code}: {message}",
            "remediation": "Review IAM permissions and role trust policies.",
        }


def check_static_credentials() -> dict[str, Any]:
    """Check whether static AWS credentials are configured (anti-pattern).

    Returns a dict indicating whether static credentials are detected.
    In production, credentials should come from task roles or instance profiles.
    """
    import os

    has_access_key = bool(os.environ.get("AWS_ACCESS_KEY_ID"))
    has_secret_key = bool(os.environ.get("AWS_SECRET_ACCESS_KEY"))
    has_session_token = bool(os.environ.get("AWS_SESSION_TOKEN"))
    has_profile = bool(os.environ.get("AWS_PROFILE"))

    static_detected = has_access_key and has_secret_key and not has_session_token

    return {
        "static_credentials_detected": static_detected,
        "has_access_key_env": has_access_key,
        "has_secret_key_env": has_secret_key,
        "has_session_token_env": has_session_token,
        "has_profile_env": has_profile,
        "compliant": not static_detected,
        "remediation": (
            "Remove AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables. "
            "Use IAM task roles (ECS) or instance profiles (EC2) for runtime credentials."
        ) if static_detected else None,
    }


def validate_full_credential_chain(
    customer_role_arn: str | None = None,
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Run full credential chain validation.

    Checks:
    1. Runtime identity (GetCallerIdentity)
    2. Static credential detection
    3. Cross-account AssumeRole (if customer_role_arn provided)
    """
    result: dict[str, Any] = {"checks": [], "overall_valid": True}

    # 1. Runtime identity
    identity = validate_runtime_identity()
    result["runtime_identity"] = identity
    result["checks"].append({
        "name": "runtime_identity",
        "passed": identity["valid"],
        "message": f"Runtime identity: {identity.get('arn', 'unknown')}",
    })
    if not identity["valid"]:
        result["overall_valid"] = False

    # 2. Static credential check
    static_check = check_static_credentials()
    result["static_credentials"] = static_check
    result["checks"].append({
        "name": "no_static_credentials",
        "passed": static_check["compliant"],
        "message": "No static AWS credentials detected" if static_check["compliant"] else "Static AWS credentials detected (anti-pattern)",
    })
    if not static_check["compliant"]:
        result["overall_valid"] = False

    # 3. AssumeRole chain
    if customer_role_arn:
        assume_result = validate_assume_role_chain(customer_role_arn, region)
        result["assume_role"] = assume_result
        result["checks"].append({
            "name": "assume_role_chain",
            "passed": assume_result["success"],
            "message": f"AssumeRole to {customer_role_arn}: {'success' if assume_result['success'] else assume_result.get('error', 'failed')}",
        })
        if not assume_result["success"]:
            result["overall_valid"] = False

    return result


def _detect_credential_source(arn: str, user_id: str) -> str:
    """Detect how AWS credentials were obtained based on caller identity."""
    if ":assumed-role/" in arn:
        # ECS task role, EKS IRSA, or other assumed role
        if "/i-" in user_id:
            return "instance_profile"
        return "task_role"
    if ":user/" in arn:
        return "static"  # IAM user = static credentials
    if ":root" in arn:
        return "root"
    return "unknown"
