import type { KioskRangeLanesResponse } from "@/types/api";

const DEVICE_TOKEN_HEADER = "x-device-token";
const DEFAULT_REQUEST_TIMEOUT_MS = 10000;

/**
 * localStorage key where the pairing flow stores the per-device token after
 * POST /v1/devices/pair completes. Import this in the pairing flow to ensure
 * both sides use the same key.
 */
export const DEVICE_TOKEN_STORAGE_KEY = "kiosk_device_token";

interface KioskRequestOptions extends Omit<RequestInit, "headers"> {
  deviceTokenOverride?: string;
  headers?: HeadersInit;
  timeoutMs?: number;
}

export class KioskApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    Object.setPrototypeOf(this, new.target.prototype);
    this.name = "KioskApiError";
    this.status = status;
  }
}

function getApiBaseUrl(): string {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!apiBase) {
    throw new KioskApiError("API base URL is not configured.", 500);
  }
  return apiBase;
}

function buildRequestUrl(apiBase: string, path: string): string {
  const normalizedBase = apiBase.endsWith("/") ? apiBase.slice(0, -1) : apiBase;
  const normalizedPath = path.startsWith("/") ? path.slice(1) : path;

  return `${normalizedBase}/${normalizedPath}`;
}

function getDeviceToken(override?: string): string {
  const storedToken =
    typeof window !== "undefined"
      ? (localStorage.getItem(DEVICE_TOKEN_STORAGE_KEY) ?? undefined)
      : undefined;
  const token = override ?? storedToken ?? process.env.NEXT_PUBLIC_DEVICE_TOKEN;
  if (!token) {
    throw new KioskApiError("Device token is not configured.", 500);
  }
  return token;
}

async function parseErrorBody(response: Response): Promise<string | null> {
  try {
    const data = (await response.json()) as { error?: string };
    return data.error ?? null;
  } catch {
    return null;
  }
}

export async function fetchKioskJson<T>(
  path: string,
  options: KioskRequestOptions = {},
): Promise<T> {
  const apiBase = getApiBaseUrl();
  const deviceToken = getDeviceToken(options.deviceTokenOverride);
  const timeoutMs = options.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;

  const headers = new Headers(options.headers);
  headers.set(DEVICE_TOKEN_HEADER, deviceToken);
  headers.set("Accept", "application/json");

  const { deviceTokenOverride: _, headers: __, timeoutMs: ___, ...fetchInit } = options;
  const timeoutController = new AbortController();
  let didTimeout = false;

  const timeoutId = setTimeout(() => {
    didTimeout = true;
    timeoutController.abort();
  }, timeoutMs);

  if (fetchInit.signal) {
    if (fetchInit.signal.aborted) {
      timeoutController.abort();
    }
    fetchInit.signal.addEventListener("abort", () => timeoutController.abort(), { once: true });
  }

  let response: Response;

  try {
    response = await fetch(buildRequestUrl(apiBase, path), {
      ...fetchInit,
      headers,
      cache: "no-store",
      signal: timeoutController.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      const status = didTimeout ? 504 : 499;
      const message = didTimeout
        ? "Kiosk request timed out. Please try again."
        : "Kiosk request was cancelled.";
      throw new KioskApiError(message, status);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    const bodyError = await parseErrorBody(response);
    const isKioskAuthForbidden =
      response.status === 403 && (!bodyError || bodyError === "Forbidden");

    const message = isKioskAuthForbidden
      ? "Device token rejected. Re-pair this kiosk device."
      : (bodyError ?? `Kiosk request failed (${response.status}).`);

    throw new KioskApiError(
      message,
      response.status,
    );
  }

  return (await response.json()) as T;
}

export async function getKioskRangeLanes(
  deviceTokenOverride?: string,
): Promise<KioskRangeLanesResponse> {
  return fetchKioskJson<KioskRangeLanesResponse>("/v1/kiosk/range/lanes", {
    method: "GET",
    deviceTokenOverride,
  });
}