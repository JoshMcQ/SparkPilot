export type AccessWorkflowStep = {
  id: string;
  title: string;
  description: string;
};

export const ACCESS_WORKFLOW_STEPS: AccessWorkflowStep[] = [
  {
    id: "token",
    title: "Authenticate",
    description:
      "Sign in via your IdP first. Manual token mode is development-only and should remain disabled in production.",
  },
  {
    id: "identity",
    title: "Map identity",
    description:
      "Create or update the user identity using the JWT subject (sub) so roles resolve automatically.",
  },
  {
    id: "team",
    title: "Create ownership",
    description: "Create a team under the tenant and assign allowed environments.",
  },
  {
    id: "budget",
    title: "Set guardrails",
    description: "Configure monthly budget + warn/block thresholds before operators dispatch runs.",
  },
];

export function validateIdentityForm(actor: string): string | null {
  if (!actor.trim()) {
    return "Actor (subject identifier) is required.";
  }
  return null;
}

export function validateTeamForm(teamName: string, tenantId: string): string | null {
  if (!teamName.trim() || !tenantId.trim()) {
    return "Team name and tenant ID are required.";
  }
  return null;
}

export function validateScopeForm(teamId: string, environmentId: string): string | null {
  if (!teamId.trim() || !environmentId.trim()) {
    return "Select both a team and an environment.";
  }
  return null;
}

const INTEGER_PATTERN = /^\d+$/;

export function validateBudgetForm(
  selectedTeam: string,
  monthlyBudget: string,
  warnPct: string,
  blockPct: string,
): string | null {
  const dollars = Number(monthlyBudget);
  if (!selectedTeam.trim() || !Number.isFinite(dollars) || dollars <= 0) {
    return "Team and a positive monthly budget (USD) are required.";
  }

  if (!INTEGER_PATTERN.test(warnPct.trim()) || !INTEGER_PATTERN.test(blockPct.trim())) {
    return "Thresholds must be integers between 1 and 100.";
  }

  const warn = Number(warnPct);
  const block = Number(blockPct);
  if (!Number.isInteger(warn) || warn < 1 || warn > 100 || !Number.isInteger(block) || block < 1 || block > 100) {
    return "Thresholds must be integers between 1 and 100.";
  }
  if (warn >= block) {
    return "Warn threshold must be lower than block threshold.";
  }
  return null;
}

export function mapAccessErrorMessage(message: string): string {
  const normalized = message.toLowerCase();

  if (
    normalized.includes("403") ||
    normalized.includes("forbidden") ||
    normalized.includes("access denied") ||
    normalized.includes("unauthorized")
  ) {
    return "Access denied. Verify the identity mapping (role, tenant, team scope) before retrying this action.";
  }

  if (normalized.includes("401") || normalized.includes("authentication")) {
    return "Authentication failed. Sign in again (IdP) or refresh the bearer token used by the Access page.";
  }

  if (normalized.includes("bootstrap") || normalized.includes("x-bootstrap-secret")) {
    return "Bootstrap failed. Use bootstrap secret only for initial admin setup, then switch to normal identity mapping.";
  }

  if (normalized.includes("422") || normalized.includes("validation")) {
    return "Validation failed. Confirm required fields and UUID/ARN formats.";
  }

  return message;
}
