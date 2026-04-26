import type { KioskRangeLanesResponse } from "@/types/api";

const DEVICE_TOKEN_HEADER = "x-device-token";

interface KioskRequestOptions extends Omit<RequestInit, "headers"> {
  deviceTokenOverride?: string;
  headers?: HeadersInit;
}

export class KioskApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
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

function getDeviceToken(override?: string): string {
  const token = override ?? process.env.NEXT_PUBLIC_DEVICE_TOKEN;
  if (!token) {
    throw new KioskApiError("Device token is not configured.", 401);
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

  const headers = new Headers(options.headers);
  headers.set(DEVICE_TOKEN_HEADER, deviceToken);
  headers.set("Accept", "application/json");

  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const { deviceTokenOverride: _, headers: __, ...fetchInit } = options;

  const response = await fetch(`${apiBase}${path}`, {
    ...fetchInit,
    headers,
    cache: "no-store",
  });

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