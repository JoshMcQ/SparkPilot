const API_BASE = (process.env.SPARKPILOT_API ?? "").trim();

export function sparkpilotApiBase(): string {
  if (!API_BASE) {
    throw new Error("Missing SPARKPILOT_API. Set the upstream SparkPilot API base URL.");
  }
  return API_BASE;
}
