#!/usr/bin/env python
"""Import SparkPilot CSV backlog into Jira Cloud using REST API v2.

Usage:
  python scripts/jira_import.py \
    --base-url https://your-domain.atlassian.net \
    --email you@example.com \
    --api-token <token> \
    --project SPARK \
    --csv planning/jira/sparkpilot_jira_import.csv

Optional env vars:
  JIRA_EPIC_NAME_FIELD_ID=customfield_10011
  JIRA_EPIC_LINK_FIELD_ID=customfield_10014
  JIRA_STORY_POINTS_FIELD_ID=customfield_10016
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

import httpx


def _split_labels(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _create_issue(
    client: httpx.Client,
    *,
    base_url: str,
    project_key: str,
    row: dict[str, str],
    key_by_external_id: dict[str, str],
    epic_name_field_id: str | None,
    epic_link_field_id: str | None,
    story_points_field_id: str | None,
) -> str:
    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "summary": row["Summary"],
        "issuetype": {"name": row["Issue Type"]},
        "description": row.get("Description", ""),
        "priority": {"name": row.get("Priority", "Medium") or "Medium"},
        "labels": _split_labels(row.get("Labels")),
    }

    if row["Issue Type"].lower() == "epic" and epic_name_field_id and row.get("Epic Name"):
        fields[epic_name_field_id] = row["Epic Name"]

    parent_external_id = row.get("Parent External ID", "")
    if parent_external_id and epic_link_field_id:
        parent_key = key_by_external_id.get(parent_external_id)
        if parent_key:
            fields[epic_link_field_id] = parent_key

    if story_points_field_id and row.get("Story Points"):
        try:
            fields[story_points_field_id] = float(row["Story Points"])
        except ValueError:
            pass

    resp = client.post(
        f"{base_url.rstrip('/')}/rest/api/2/issue",
        json={"fields": fields},
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload["key"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Import SparkPilot CSV backlog into Jira")
    parser.add_argument("--base-url", required=True, help="Jira base URL, e.g. https://example.atlassian.net")
    parser.add_argument("--email", required=True, help="Jira user email")
    parser.add_argument("--api-token", required=True, help="Jira API token")
    parser.add_argument("--project", required=True, help="Jira project key")
    parser.add_argument("--csv", required=True, help="Path to CSV backlog file")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    epic_name_field_id = os.getenv("JIRA_EPIC_NAME_FIELD_ID")
    epic_link_field_id = os.getenv("JIRA_EPIC_LINK_FIELD_ID")
    story_points_field_id = os.getenv("JIRA_STORY_POINTS_FIELD_ID")

    with csv_path.open("r", newline="", encoding="utf-8") as fp:
        rows = list(csv.DictReader(fp))

    # Create epics first, then non-epics.
    epic_rows = [row for row in rows if row.get("Issue Type", "").lower() == "epic"]
    non_epic_rows = [row for row in rows if row.get("Issue Type", "").lower() != "epic"]
    ordered_rows = epic_rows + non_epic_rows

    key_by_external_id: dict[str, str] = {}
    created: list[dict[str, str]] = []

    with httpx.Client(auth=(args.email, args.api_token), timeout=30.0) as client:
        for row in ordered_rows:
            external_id = row["External ID"]
            key = _create_issue(
                client,
                base_url=args.base_url,
                project_key=args.project,
                row=row,
                key_by_external_id=key_by_external_id,
                epic_name_field_id=epic_name_field_id,
                epic_link_field_id=epic_link_field_id,
                story_points_field_id=story_points_field_id,
            )
            key_by_external_id[external_id] = key
            created.append({"external_id": external_id, "issue_key": key, "summary": row["Summary"]})

    print(json.dumps({"created": created}, indent=2))


if __name__ == "__main__":
    main()

