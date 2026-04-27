import type { KioskRangeLanesResponse } from "@/types/api";

const KIOSK_PROXY_BASE_PATH = "/api/kiosk/proxy";
const DEFAULT_REQUEST_TIMEOUT_MS = 10000;

interface KioskRequestOptions extends Omit<RequestInit, "headers"> {
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

function buildProxyPath(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${KIOSK_PROXY_BASE_PATH}${normalizedPath}`;
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
  const timeoutMs = options.timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;

  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");

  const { headers: _, timeoutMs: __, ...fetchInit } = options;
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
    response = await fetch(buildProxyPath(path), {
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

export async function getKioskRangeLanes(): Promise<KioskRangeLanesResponse> {
  return fetchKioskJson<KioskRangeLanesResponse>("/v1/kiosk/range/lanes", {
    method: "GET",
  });
}