"use client";

import { shortId } from "@/lib/format";

/**
 * Renders a truncated ID with a styled tooltip showing the full value on hover.
 * Falls back gracefully for empty/null values.
 */
export function ShortId({ value, className }: { value: string | null | undefined; className?: string }) {
  const raw = value ?? "-";
  const display = raw === "-" ? "-" : shortId(raw);
  const showTooltip = raw.length > 8;

  return (
    <span className={`short-id ${className ?? ""}`} title={showTooltip ? raw : undefined}>
      {display}
      {showTooltip && <span className="short-id-tooltip" aria-hidden>{raw}</span>}
    </span>
  );
}
