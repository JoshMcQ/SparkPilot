import { createHash, createHmac, randomUUID, timingSafeEqual } from "crypto";

export const CONTACT_FORM_TOKEN_TTL_MS = 30 * 60 * 1000;
export const MIN_CONTACT_SUBMIT_TOKEN_LENGTH = 32;

function firstForwardedValue(value: string | null): string {
  const parts = (value ?? "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  return parts[0] ?? "";
}

export function contactSubmitSecretFromEnv(): string {
  const secret = (process.env.SPARKPILOT_CONTACT_SUBMIT_TOKEN ?? "").trim();
  if (secret.length < MIN_CONTACT_SUBMIT_TOKEN_LENGTH) {
    throw new Error("Missing SPARKPILOT_CONTACT_SUBMIT_TOKEN.");
  }
  return secret;
}

export function clientFingerprintFromHeaders(headers: Headers): string {
  const ip =
    firstForwardedValue(headers.get("X-Forwarded-For")) ||
    (headers.get("X-Real-IP") ?? "").trim() ||
    "unknown";
  const userAgent = (headers.get("User-Agent") ?? "unknown").slice(0, 160);
  return createHash("sha256").update(`${ip}:${userAgent}`).digest("base64url");
}

function signatureFor(secret: string, expiresAt: number, nonce: string, fingerprint: string): string {
  return createHmac("sha256", secret)
    .update(`v1:${expiresAt}:${nonce}:${fingerprint}`)
    .digest("base64url");
}

function safeEqual(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

export function createContactFormToken(
  secret: string,
  fingerprint: string,
  nowMs = Date.now(),
): string {
  const expiresAt = nowMs + CONTACT_FORM_TOKEN_TTL_MS;
  const nonce = randomUUID();
  const signature = signatureFor(secret, expiresAt, nonce, fingerprint);
  return `v1.${expiresAt}.${nonce}.${signature}`;
}

export function isContactFormTokenValid(
  token: string,
  secret: string,
  fingerprint: string,
  nowMs = Date.now(),
): boolean {
  const parts = token.split(".");
  if (parts.length !== 4 || parts[0] !== "v1") {
    return false;
  }

  const expiresAt = Number.parseInt(parts[1] ?? "", 10);
  const nonce = parts[2] ?? "";
  const suppliedSignature = parts[3] ?? "";
  if (!Number.isSafeInteger(expiresAt) || expiresAt < nowMs || !nonce || !suppliedSignature) {
    return false;
  }

  const expectedSignature = signatureFor(secret, expiresAt, nonce, fingerprint);
  return safeEqual(suppliedSignature, expectedSignature);
}
