from sparkpilot.services.preflight import _upsert_preflight_check


def test_upsert_preflight_check_deduplicates_same_code() -> None:
    checks: list[dict] = []

    _upsert_preflight_check(
        checks,
        code="byoc_lite.example",
        status_value="pass",
        message="first",
    )
    _upsert_preflight_check(
        checks,
        code="byoc_lite.example",
        status_value="pass",
        message="second",
    )

    assert len(checks) == 1
    assert checks[0]["status"] == "pass"
    assert checks[0]["message"] == "first"


def test_upsert_preflight_check_promotes_severity_to_fail() -> None:
    checks: list[dict] = []

    _upsert_preflight_check(
        checks,
        code="issue18.dispatch",
        status_value="pass",
        message="ok",
    )
    _upsert_preflight_check(
        checks,
        code="issue18.dispatch",
        status_value="fail",
        message="denied",
        remediation="grant action",
    )

    assert len(checks) == 1
    assert checks[0]["status"] == "fail"
    assert checks[0]["message"] == "denied"
    assert checks[0]["remediation"] == "grant action"


def test_upsert_preflight_check_does_not_demote_fail() -> None:
    checks: list[dict] = []

    _upsert_preflight_check(
        checks,
        code="issue18.namespace",
        status_value="fail",
        message="invalid",
        remediation="use dns-1123 name",
    )
    _upsert_preflight_check(
        checks,
        code="issue18.namespace",
        status_value="pass",
        message="ok",
    )

    assert len(checks) == 1
    assert checks[0]["status"] == "fail"
    assert checks[0]["message"] == "invalid"
    assert checks[0]["remediation"] == "use dns-1123 name"


def test_upsert_preflight_check_keeps_distinct_policy_ids() -> None:
    checks: list[dict] = []

    _upsert_preflight_check(
        checks,
        code="policy.team_budget",
        status_value="fail",
        message="team alpha exceeded budget",
        details={"policy_id": "policy-alpha"},
    )
    _upsert_preflight_check(
        checks,
        code="policy.team_budget",
        status_value="fail",
        message="team beta exceeded budget",
        details={"policy_id": "policy-beta"},
    )

    assert len(checks) == 2
    assert checks[0]["details"]["policy_id"] == "policy-alpha"
    assert checks[1]["details"]["policy_id"] == "policy-beta"
