import {
  KioskApiError,
  fetchKioskJson,
  getKioskRangeLanes,
} from "@/lib/kioskApi";

describe("kioskApi", () => {
  const originalApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  const originalDeviceToken = process.env.NEXT_PUBLIC_DEVICE_TOKEN;
  const originalFetch = global.fetch;

  beforeEach(() => {
    jest.resetAllMocks();
    if (originalApiBaseUrl === undefined) {
      delete process.env.NEXT_PUBLIC_API_BASE_URL;
    } else {
      process.env.NEXT_PUBLIC_API_BASE_URL = originalApiBaseUrl;
    }

    if (originalDeviceToken === undefined) {
      delete process.env.NEXT_PUBLIC_DEVICE_TOKEN;
    } else {
      process.env.NEXT_PUBLIC_DEVICE_TOKEN = originalDeviceToken;
    }

    global.fetch = originalFetch;
  });

  afterAll(() => {
    if (originalApiBaseUrl === undefined) {
      delete process.env.NEXT_PUBLIC_API_BASE_URL;
    } else {
      process.env.NEXT_PUBLIC_API_BASE_URL = originalApiBaseUrl;
    }

    if (originalDeviceToken === undefined) {
      delete process.env.NEXT_PUBLIC_DEVICE_TOKEN;
    } else {
      process.env.NEXT_PUBLIC_DEVICE_TOKEN = originalDeviceToken;
    }

    global.fetch = originalFetch;
  });

  it("throws when API base URL is missing", async () => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    process.env.NEXT_PUBLIC_DEVICE_TOKEN = "token-123";

    await expect(fetchKioskJson("/v1/kiosk/range/lanes")).rejects.toMatchObject({
      name: "KioskApiError",
      status: 500,
    });
  });

  it("throws when device token is missing", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://example.test";
    delete process.env.NEXT_PUBLIC_DEVICE_TOKEN;

    await expect(fetchKioskJson("/v1/kiosk/range/lanes")).rejects.toMatchObject({
      name: "KioskApiError",
      status: 500,
    });
  });

  it("sends x-device-token header and returns JSON", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://example.test";
    process.env.NEXT_PUBLIC_DEVICE_TOKEN = "device-token-abc";

    const mockResponse = {
      range_id: "r1",
      name: "Rifle-Pistol",
      is_open: true,
      lanes: [],
    };

    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });

    global.fetch = fetchMock as unknown as typeof fetch;

    const result = await getKioskRangeLanes();

    expect(result).toEqual(mockResponse);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://example.test/v1/kiosk/range/lanes");
    expect(options.method).toBe("GET");
    const headers = options.headers as Headers;
    expect(headers.get("x-device-token")).toBe("device-token-abc");
    expect(headers.get("Accept")).toBe("application/json");
  });

  it("maps non-OK responses to KioskApiError", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://example.test";
    process.env.NEXT_PUBLIC_DEVICE_TOKEN = "device-token-abc";

    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ error: "Device token revoked" }),
    });

    global.fetch = fetchMock as unknown as typeof fetch;

    const request = getKioskRangeLanes();

    await expect(request).rejects.toBeInstanceOf(KioskApiError);
    await expect(request).rejects.toMatchObject({
      status: 403,
      message: "Device token revoked",
    });
  });

  it("normalizes URL construction when API base URL has a trailing slash", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://example.test/";
    process.env.NEXT_PUBLIC_DEVICE_TOKEN = "device-token-abc";

    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ range_id: "r1", name: "Rifle-Pistol", is_open: true, lanes: [] }),
    });

    global.fetch = fetchMock as unknown as typeof fetch;

    await getKioskRangeLanes();

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://example.test/v1/kiosk/range/lanes");
  });

  it("preserves API Gateway stage segments in the configured base URL", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://example.test/prod";
    process.env.NEXT_PUBLIC_DEVICE_TOKEN = "device-token-abc";

    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ range_id: "r1", name: "Rifle-Pistol", is_open: true, lanes: [] }),
    });

    global.fetch = fetchMock as unknown as typeof fetch;

    await getKioskRangeLanes();

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://example.test/prod/v1/kiosk/range/lanes");
  });

  it("maps timed-out requests to a timeout kiosk error", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://example.test";
    process.env.NEXT_PUBLIC_DEVICE_TOKEN = "device-token-abc";

    const fetchMock = jest.fn().mockImplementation((_: string, init?: RequestInit) =>
      new Promise((_, reject) => {
        const signal = init?.signal;
        signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted.", "AbortError"));
        });
      }));

    global.fetch = fetchMock as unknown as typeof fetch;

    await expect(fetchKioskJson("/v1/kiosk/range/lanes", { timeoutMs: 1 })).rejects.toMatchObject({
      status: 504,
      message: "Kiosk request timed out. Please try again.",
    });
  });

  it("honors an already-aborted caller signal before starting the request", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://example.test";
    process.env.NEXT_PUBLIC_DEVICE_TOKEN = "device-token-abc";

    const controller = new AbortController();
    controller.abort();

    const fetchMock = jest.fn().mockRejectedValue(
      new DOMException("The operation was aborted.", "AbortError"),
    );

    global.fetch = fetchMock as unknown as typeof fetch;

    await expect(fetchKioskJson("/v1/kiosk/range/lanes", { signal: controller.signal })).rejects.toMatchObject({
      status: 499,
      message: "Kiosk request was cancelled.",
    });
  });

  it("maps masked Forbidden auth responses to kiosk pairing guidance", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://example.test";
    process.env.NEXT_PUBLIC_DEVICE_TOKEN = "device-token-abc";

    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ error: "Forbidden" }),
    });

    global.fetch = fetchMock as unknown as typeof fetch;

    await expect(getKioskRangeLanes()).rejects.toMatchObject({
      status: 403,
      message: "Device token rejected. Re-pair this kiosk device.",
    });
  });
});
