import test from "node:test";
import assert from "node:assert/strict";

import {
  ACCESS_WORKFLOW_STEPS,
  mapAccessErrorMessage,
  validateBudgetForm,
  validateIdentityForm,
  validateScopeForm,
  validateTeamForm,
} from "../lib/access-workflow";

test("guided workflow exposes 4 ordered admin steps", () => {
  assert.equal(ACCESS_WORKFLOW_STEPS.length, 4);
  assert.deepEqual(
    ACCESS_WORKFLOW_STEPS.map((step) => step.id),
    ["token", "identity", "team", "budget"],
  );
});

test("identity validation requires actor subject", () => {
  assert.equal(validateIdentityForm(""), "Actor (subject identifier) is required.");
  assert.equal(validateIdentityForm("   "), "Actor (subject identifier) is required.");
  assert.equal(validateIdentityForm("user:demo-admin"), null);
});

test("team validation requires team name and tenant", () => {
  assert.equal(validateTeamForm("", "tenant-1"), "Team name and tenant ID are required.");
  assert.equal(validateTeamForm("data", ""), "Team name and tenant ID are required.");
  assert.equal(validateTeamForm("data", "tenant-1"), null);
});

test("scope validation requires team and environment selection", () => {
  assert.equal(validateScopeForm("", "env-1"), "Select both a team and an environment.");
  assert.equal(validateScopeForm("team-1", ""), "Select both a team and an environment.");
  assert.equal(validateScopeForm("   ", "env-1"), "Select both a team and an environment.");
  assert.equal(validateScopeForm("team-1", "   "), "Select both a team and an environment.");
  assert.equal(validateScopeForm("team-1", "env-1"), null);
});

test("budget validation checks positive budget and threshold bounds", () => {
  assert.equal(
    validateBudgetForm("", "100", "80", "100"),
    "Team and a positive monthly budget (USD) are required.",
  );
  assert.equal(
    validateBudgetForm("team", "0", "80", "100"),
    "Team and a positive monthly budget (USD) are required.",
  );
  assert.equal(
    validateBudgetForm("team", "100", "80abc", "100"),
    "Thresholds must be integers between 1 and 100.",
  );
  assert.equal(
    validateBudgetForm("team", "100", "90", "80"),
    "Warn threshold must be lower than block threshold.",
  );
  assert.equal(validateBudgetForm("team", "100", "80", "100"), null);
});

test("error mapping provides actionable auth/bootstrap guidance", () => {
  assert.match(mapAccessErrorMessage("401 authentication failed"), /Authentication failed/i);
  assert.match(mapAccessErrorMessage("401 unauthorized"), /Access denied/i);
  assert.match(mapAccessErrorMessage("403 forbidden"), /Access denied/i);
  assert.match(mapAccessErrorMessage("bootstrap secret invalid"), /Bootstrap failed/i);
  assert.match(mapAccessErrorMessage("422 validation failed"), /Validation failed/i);
  assert.equal(mapAccessErrorMessage("network timeout"), "network timeout");
});
