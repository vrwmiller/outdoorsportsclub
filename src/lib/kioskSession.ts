export const KIOSK_DEVICE_TOKEN_COOKIE = "kiosk_device_token";

export function getKioskApiBaseUrl(): string {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!apiBase) {
    throw new Error("API base URL is not configured.");
  }
  return apiBase.endsWith("/") ? apiBase.slice(0, -1) : apiBase;
}
