/** Shared display formatting helpers used across UI pages. */

/** Truncate a UUID to its first 8 characters for display. */
export function shortId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) : id;
}

/** Build a human-readable label for an environment from its metadata. */
export function envLabel(env: { id: string; region: string; eks_namespace: string | null; provisioning_mode: string }): string {
  const ns = env.eks_namespace ?? env.provisioning_mode;
  return `${env.region} / ${ns}  (${shortId(env.id)})`;
}

/** Format a UTC ISO timestamp to a compact locale-friendly string. */
export function compactTime(iso: string | null): string {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return iso;
  }
}

/** Format microdollars as a USD string. */
export function usd(micros: number | null | undefined): string {
  const value = Number(micros ?? 0) / 1_000_000;
  return `$${value.toFixed(4)}`;
}

/** Friendly error message derived from an API error. */
export function friendlyError(err: unknown, fallback: string): string {
  if (err instanceof Error) {
    const msg = err.message;
    // Extract the detail portion from structured API errors
    const detailMatch = msg.match(/\(\d+\):\s*(.+)/);
    if (detailMatch) return detailMatch[1];
    // Map raw status codes to guidance
    if (msg.includes("500")) return `${fallback}. The server encountered an internal error — check API logs or retry.`;
    if (msg.includes("502") || msg.includes("503")) return `${fallback}. The API is unreachable — verify the backend is running.`;
    if (msg.includes("401")) return `${fallback}. Authentication failed — check your OIDC credentials.`;
    if (msg.includes("403")) return `${fallback}. Access denied — verify your role and team scope.`;
    if (msg.includes("404")) return `${fallback}. Resource not found — it may have been deleted.`;
    if (msg.includes("409")) return `${fallback}. A conflicting resource already exists.`;
    if (msg.includes("422")) return `${fallback}. Validation failed — check the request fields.`;
    return msg;
  }
  return fallback;
}
