const APP_URL_RAW = process.env.NEXT_PUBLIC_APP_URL || "https://app.sparkpilot.cloud";
export const APP_URL = APP_URL_RAW.replace(/\/+$/, "");

export function appHref(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${APP_URL}${normalized}`;
}
