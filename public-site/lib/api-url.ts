const API_URL_RAW = process.env.NEXT_PUBLIC_API_URL || "https://api.sparkpilot.cloud";
export const API_URL = API_URL_RAW.replace(/\/+$/, "");
