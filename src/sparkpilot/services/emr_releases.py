"""EMR release label management and synchronisation."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from sparkpilot.audit import write_audit_event
from sparkpilot.aws_clients import EmrEksClient
from sparkpilot.config import get_settings
from sparkpilot.models import EmrRelease
from sparkpilot.services._helpers import _now


# ---------------------------------------------------------------------------
# Release label utilities
# ---------------------------------------------------------------------------

def _parse_release_version(label: str) -> tuple[int, int, int] | None:
    match = re.match(r"^emr-(\d+)\.(\d+)\.(\d+)(?:-.+)?$", label)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _canonical_release_label(label: str) -> str:
    return label.removesuffix("-latest")


def _graviton_supported_for_label(label: str) -> bool:
    version = _parse_release_version(label)
    if not version:
        return False
    return version >= (6, 9, 0)


def _lake_formation_supported_for_label(label: str) -> bool:
    version = _parse_release_version(label)
    if not version:
        return False
    return version >= (7, 7, 0)


# ---------------------------------------------------------------------------
# CRUD / sync
# ---------------------------------------------------------------------------

def list_emr_releases(db: Session, *, limit: int = 200, offset: int = 0) -> list[EmrRelease]:
    rows = list(db.execute(select(EmrRelease)).scalars())
    # Keep unknown/non-standard labels at the bottom by using (0,0,0) fallback.
    ordered = sorted(
        rows,
        key=lambda row: (_parse_release_version(row.release_label) or (0, 0, 0), row.release_label),
        reverse=True,
    )
    return ordered[offset:offset + limit]


def sync_emr_releases_once(db: Session, *, actor: str = "worker:emr-release-sync") -> int:
    settings = get_settings()
    client = EmrEksClient()
    labels = sorted(set(client.list_release_labels(settings.aws_region)), reverse=True)
    if not labels:
        return 0

    parsed = [(label, _parse_release_version(label)) for label in labels]
    valid = [item for item in parsed if item[1] is not None]
    valid.sort(key=lambda item: item[1], reverse=True)
    latest_label = valid[0][0] if valid else labels[0]

    current_labels = {item[0] for item in valid[:3]}
    changed = 0
    now = _now()
    for label, version in parsed:
        status_value = "deprecated"
        if label in current_labels:
            status_value = "current"
        if version and valid:
            newest = valid[0][1]
            if newest and version[0] < newest[0]:
                status_value = "end_of_life"

        row = db.execute(select(EmrRelease).where(EmrRelease.release_label == label)).scalar_one_or_none()
        is_new = row is None
        if is_new:
            row = EmrRelease(release_label=label)
            db.add(row)

        previous = (
            row.lifecycle_status,
            row.graviton_supported,
            row.lake_formation_supported,
            row.upgrade_target,
        )
        row.lifecycle_status = status_value
        row.graviton_supported = _graviton_supported_for_label(label)
        row.lake_formation_supported = _lake_formation_supported_for_label(label)
        row.upgrade_target = None if status_value == "current" else latest_label
        row.source = "emr-containers"
        row.last_synced_at = now
        current = (
            row.lifecycle_status,
            row.graviton_supported,
            row.lake_formation_supported,
            row.upgrade_target,
        )
        if is_new or current != previous:
            changed += 1

    write_audit_event(
        db,
        actor=actor,
        action="emr_release.sync",
        entity_type="system",
        entity_id="emr_releases",
        details={
            "region": settings.aws_region,
            "release_count": len(labels),
            "latest_release_label": latest_label,
        },
    )
    db.commit()
    return changed
