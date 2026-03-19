"""Lake Formation Fine-Grained Access Control (FGAC) integration (#38).

Provides:
- FGAC preflight checks for EMR-on-EKS environments
- Lake Formation permission validation
- Service-linked role detection
- Audit context for active LF permissions during run execution
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

import botocore.exceptions

from sparkpilot.config import get_settings
from sparkpilot.services.emr_releases import _lake_formation_supported_for_label

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from sparkpilot.models import Environment

logger = logging.getLogger(__name__)

# Minimum EMR release that supports FGAC
_MIN_LF_RELEASE = "emr-7.7.0"


# ---------------------------------------------------------------------------
# AWS Lake Formation helpers
# ---------------------------------------------------------------------------

def _get_lf_client(region: str) -> Any:
    """Return a boto3 Lake Formation client for the given region."""
    import boto3

    return boto3.client("lakeformation", region_name=region)


def _get_iam_client(region: str) -> Any:
    """Return a boto3 IAM client."""
    import boto3

    return boto3.client("iam", region_name=region)


def check_lf_service_linked_role_exists(region: str) -> dict[str, Any]:
    """Check whether the required LF service-linked role exists.

    AWS Lake Formation uses a service-linked role
    (AWSServiceRoleForLakeFormationDataAccess) to access data on behalf
    of principals.
    """
    slr_name = "AWSServiceRoleForLakeFormationDataAccess"
    try:
        iam = _get_iam_client(region)
        iam.get_role(RoleName=slr_name)
        return {"exists": True, "role_name": slr_name, "error": None}
    except botocore.exceptions.ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "NoSuchEntity":
            return {"exists": False, "role_name": slr_name, "error": None}
        return {"exists": False, "role_name": slr_name, "error": str(exc)}
    except Exception as exc:
        return {"exists": False, "role_name": slr_name, "error": str(exc)}


def check_execution_role_lf_permissions(
    region: str,
    execution_role_arn: str,
    catalog_id: str | None = None,
) -> dict[str, Any]:
    """Validate that the execution role has Lake Formation data permissions.

    Calls lakeformation:ListPermissions filtered by the execution role
    principal. Returns a summary of granted permissions found.
    """
    try:
        lf = _get_lf_client(region)
        principal = {"DataLakePrincipal": {"DataLakePrincipalIdentifier": execution_role_arn}}
        kwargs: dict[str, Any] = {"Principal": principal}
        if catalog_id:
            kwargs["CatalogId"] = catalog_id

        permissions: list[dict] = []
        paginator = lf.get_paginator("list_permissions")
        for page in paginator.paginate(**kwargs):
            permissions.extend(page.get("PrincipalResourcePermissions", []))

        databases = set()
        tables = set()
        for perm in permissions:
            resource = perm.get("Resource", {})
            if "Database" in resource:
                databases.add(resource["Database"].get("Name", ""))
            if "Table" in resource:
                tables.add(resource["Table"].get("Name", ""))

        return {
            "has_permissions": len(permissions) > 0,
            "permission_count": len(permissions),
            "databases": sorted(databases),
            "tables": sorted(tables),
            "error": None,
        }
    except botocore.exceptions.ClientError as exc:
        return {
            "has_permissions": False,
            "permission_count": 0,
            "databases": [],
            "tables": [],
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "has_permissions": False,
            "permission_count": 0,
            "databases": [],
            "tables": [],
            "error": str(exc),
        }


def get_lf_permission_context(
    region: str,
    execution_role_arn: str,
    catalog_id: str | None = None,
) -> dict[str, Any]:
    """Build the LF permission context dict for audit trail recording.

    This is called during run creation to capture the active Lake Formation
    permission state at the time the run starts.
    """
    perm_result = check_execution_role_lf_permissions(
        region, execution_role_arn, catalog_id=catalog_id,
    )
    return {
        "lake_formation_enabled": True,
        "catalog_id": catalog_id or "default",
        "execution_role_arn": execution_role_arn,
        "has_permissions": perm_result["has_permissions"],
        "permission_count": perm_result["permission_count"],
        "databases": perm_result["databases"],
        "tables": perm_result["tables"],
        "checked_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------


def _add_release_compatibility_check(configured_release: str, add_check: Callable[..., None]) -> None:
    if configured_release:
        if _lake_formation_supported_for_label(configured_release):
            add_check(
                code="fgac.emr_release",
                status_value="pass",
                message=f"EMR release {configured_release} supports Lake Formation FGAC.",
                details={"emr_release_label": configured_release},
            )
            return
        add_check(
            code="fgac.emr_release",
            status_value="fail",
            message=(
                f"EMR release {configured_release} does not support Lake Formation FGAC. "
                f"Minimum required: {_MIN_LF_RELEASE}."
            ),
            remediation=f"Upgrade EMR release to {_MIN_LF_RELEASE} or later.",
            details={"emr_release_label": configured_release, "min_required": _MIN_LF_RELEASE},
        )
        return
    add_check(
        code="fgac.emr_release",
        status_value="fail",
        message="No EMR release label configured; cannot verify Lake Formation FGAC support.",
        remediation=f"Set SPARKPILOT_EMR_RELEASE_LABEL to {_MIN_LF_RELEASE} or later.",
    )


def _add_service_linked_role_check(environment: "Environment", add_check: Callable[..., None]) -> None:
    try:
        slr_result = check_lf_service_linked_role_exists(environment.region)
        if slr_result["exists"]:
            add_check(
                code="fgac.service_linked_role",
                status_value="pass",
                message="Lake Formation service-linked role exists.",
                details={"role_name": slr_result["role_name"]},
            )
            return
        message = "Lake Formation service-linked role not found."
        if slr_result["error"]:
            message += f" ({slr_result['error']})"
        add_check(
            code="fgac.service_linked_role",
            status_value="fail",
            message=message,
            remediation=(
                "Create the service-linked role: aws iam create-service-linked-role "
                "--aws-service-name lakeformation.amazonaws.com"
            ),
        )
    except Exception as exc:
        add_check(
            code="fgac.service_linked_role",
            status_value="warning",
            message=f"Unable to check Lake Formation service-linked role: {exc}",
            remediation="Ensure SparkPilot has iam:GetRole permission.",
        )


def _add_execution_role_permissions_check(
    *,
    environment: "Environment",
    execution_role_arn: str,
    add_check: Callable[..., None],
) -> None:
    catalog_id = getattr(environment, "lf_catalog_id", None)
    if not execution_role_arn:
        add_check(
            code="fgac.lf_permissions",
            status_value="warning",
            message="No execution role configured; cannot verify Lake Formation permissions.",
            remediation="Set SPARKPILOT_EMR_EXECUTION_ROLE_ARN.",
        )
        return
    try:
        perm_result = check_execution_role_lf_permissions(
            environment.region, execution_role_arn, catalog_id=catalog_id,
        )
        if perm_result["error"]:
            add_check(
                code="fgac.lf_permissions",
                status_value="warning",
                message=f"Could not verify LF permissions: {perm_result['error']}",
                remediation="Ensure SparkPilot has lakeformation:ListPermissions permission.",
            )
            return
        if perm_result["has_permissions"]:
            add_check(
                code="fgac.lf_permissions",
                status_value="pass",
                message=(
                    f"Execution role has {perm_result['permission_count']} "
                    f"Lake Formation permission(s)."
                ),
                details={
                    "permission_count": perm_result["permission_count"],
                    "databases": len(perm_result["databases"]),
                    "tables": len(perm_result["tables"]),
                },
            )
            return
        add_check(
            code="fgac.lf_permissions",
            status_value="fail",
            message="Execution role has no Lake Formation data permissions.",
            remediation=(
                "Grant Lake Formation permissions to the execution role using the "
                "AWS Lake Formation console or grant-permissions CLI command."
            ),
        )
    except Exception as exc:
        add_check(
            code="fgac.lf_permissions",
            status_value="warning",
            message=f"Unable to check Lake Formation permissions: {exc}",
        )


def _add_lake_formation_fgac_checks(
    *,
    environment: "Environment",
    db: "Session | None",
    add_check: Callable[..., None],
) -> None:
    """Add Lake Formation FGAC preflight checks when enabled."""
    if not getattr(environment, "lake_formation_enabled", False):
        return

    settings = get_settings()
    _add_release_compatibility_check(settings.emr_release_label.strip(), add_check)
    _add_service_linked_role_check(environment, add_check)
    _add_execution_role_permissions_check(
        environment=environment,
        execution_role_arn=settings.emr_execution_role_arn,
        add_check=add_check,
    )
