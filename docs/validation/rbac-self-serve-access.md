# R12: RBAC and Multi-Tenancy for Self-Serve Access

Date: March 3, 2026

## Scope Delivered

- Added role-aware identity model with `admin`, `operator`, `user`.
- Added DB role integrity constraint on `user_identities.role`.
- Added team model and team-to-environment scope mapping.
- Enforced API authorization with `403` on unauthorized access.
- Added run ownership tracking (`runs.created_by_actor`) so `user` actors can only view their own runs.
- Preserved legacy behavior when no user identities exist (backward-compatible bootstrap mode).

## Data Model Additions

- `teams`
- `user_identities`
- `team_environment_scopes`
- `runs.created_by_actor` (SQLite lightweight migration included)
- `user_identities.role` CHECK constraint (`admin`/`operator`/`user`) on newly created schemas
- Note: existing databases upgraded via lightweight `ALTER TABLE` paths do not get this CHECK retroactively.

## API Surface Added

- `GET /v1/teams`
- `POST /v1/teams`
- `GET /v1/user-identities`
- `POST /v1/user-identities`
- `GET /v1/teams/{team_id}/environments`
- `POST /v1/teams/{team_id}/environments/{environment_id}`

## Authorization Behavior

- `admin`: manage tenants/environments/golden paths/budgets/identities/scopes.
- `operator`: team-scoped environment/run visibility, can submit runs, cannot manage admin-only resources.
- `user`: can submit runs in authorized environments and view only runs they created.
- Team-scoped roles (`operator`, `user`) require explicit `team_environment_scopes` mappings. If a team has no scope mappings, environment access is denied.
- Job submission policy: jobs are environment-scoped; users can submit runs against any job within environments they are authorized to access.

## Test Evidence

- `tests/test_rbac.py::test_rbac_user_cannot_view_other_team_runs`
- `tests/test_rbac.py::test_rbac_role_permissions_admin_operator_user`
- `tests/test_rbac.py::test_rbac_admin_with_identity_can_list_runs`
- `tests/test_rbac.py::test_rbac_legacy_mode_without_user_identities`
- `tests/test_rbac.py::test_user_identity_role_check_constraint_rejects_invalid_value`

Full suite:

- `python -m pytest -q tests -p no:cacheprovider` -> `79 passed`
