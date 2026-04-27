"""SparkPilot service layer.

Sub-modules
-----------
_helpers        Shared constants, time utilities, entity lookups.
crud            Entity CRUD operations (tenants, teams, environments, jobs, runs).
diagnostics     Run diagnostic pattern matching and CloudWatch log analysis.
emr_releases    EMR release label management and synchronisation.
finops          Financial operations: budgets, cost allocation, CUR reconciliation.
golden_paths    Golden path template management and seeding.
preflight           Environment and run preflight checks with TTL caching.
preflight_byoc      BYOC-Lite specific preflight checks (split from preflight).
workers             Background worker processes — thin re-export facade.
workers_common      Shared worker claim/release helpers and transient error detection.
workers_provisioning  Provisioning worker.
workers_scheduling  Scheduler worker.
workers_reconciliation  Reconciler worker.

Only names consumed by code *outside* this package (api.py, tests, workers
entry-point) are re-exported here.  Internal cross-sub-module imports use
direct ``from sparkpilot.services.<submodule> import …`` paths.
"""

# --- Re-export third-party / sibling names that tests monkeypatch via
#     ``sparkpilot.services.X`` paths. ---
import boto3 as boto3  # noqa: F401
from sparkpilot.aws_clients import CloudWatchLogsProxy, EmrEksClient  # noqa: F401
from sparkpilot.db import SessionLocal  # noqa: F401
from sparkpilot.terraform_orchestrator import TerraformOrchestrator  # noqa: F401

# --- _helpers (only externally-consumed names) ---
from sparkpilot.services._helpers import model_to_dict  # noqa: F401

# --- crud ---
from sparkpilot.services.crud import (  # noqa: F401
    add_team_environment_scope,
    remove_team_environment_scope,
    cancel_run,
    create_environment,
    delete_environment,
    create_job,
    create_or_update_user_identity,
    create_run,
    create_team,
    create_tenant,
    fetch_run_logs,
    get_environment,
    get_environment_preflight,
    get_provisioning_operation,
    get_run,
    get_usage,
    list_environments,
    list_jobs,
    list_runs,
    list_team_environment_scopes,
    list_teams,
    list_user_identities,
    retry_environment_provisioning,
)

# --- internal_admin ---
from sparkpilot.services.internal_admin import (  # noqa: F401
    INVITE_ACCEPT_PURPOSE,
    apply_invite_identity_mapping,
    consume_invite_callback_state,
    consume_invite_token,
    create_tenant_with_admin_invite,
    get_internal_tenant_detail,
    hash_magic_link_token,
    list_internal_tenant_summaries,
    regenerate_user_invite,
)

# --- diagnostics ---
from sparkpilot.services.diagnostics import (  # noqa: F401
    _diagnostics_from_log_lines,
    list_run_diagnostics,
)

# --- emr_releases ---
from sparkpilot.services.emr_releases import (  # noqa: F401
    list_emr_releases,
    sync_emr_releases_once,
)

# --- finops ---
from sparkpilot.services.finops import (  # noqa: F401
    _record_usage_if_needed,
    create_or_update_team_budget,
    get_cost_showback,
    get_team_budget,
    process_cur_reconciliation_once,
)

# --- golden_paths ---
from sparkpilot.services.golden_paths import (  # noqa: F401
    _golden_path_to_response_payload,
    create_golden_path,
    ensure_default_golden_paths,
    get_golden_path,
    list_golden_paths,
)

# --- preflight ---
from sparkpilot.services.preflight import _build_preflight  # noqa: F401

# --- workers ---
from sparkpilot.services.workers import (  # noqa: F401
    process_provisioning_once,
    process_reconciler_once,
    process_scheduler_once,
)
