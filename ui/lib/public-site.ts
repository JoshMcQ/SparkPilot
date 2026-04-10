const DEFAULT_PUBLIC_SITE_URL = "https://sparkpilot.cloud";

function _trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export function publicSiteBaseUrl(): string {
  const raw = (process.env.NEXT_PUBLIC_MARKETING_SITE_URL ?? DEFAULT_PUBLIC_SITE_URL).trim();
  if (!raw) return DEFAULT_PUBLIC_SITE_URL;
  return _trimTrailingSlash(raw);
}

export function publicSiteHref(path = "/"): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${publicSiteBaseUrl()}${normalizedPath}`;
}
