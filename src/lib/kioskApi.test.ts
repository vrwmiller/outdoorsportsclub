import {
  KioskApiError,
  fetchKioskJson,
  getKioskRangeLanes,
} from "@/lib/kioskApi";

describe("kioskApi", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    jest.resetAllMocks();
    global.fetch = originalFetch;
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  it("calls kiosk proxy and returns JSON", async () => {
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
    expect(url).toBe("/api/kiosk/proxy/v1/kiosk/range/lanes");
    expect(options.method).toBe("GET");
    const headers = options.headers as Headers;
    expect(headers.get("Accept")).toBe("application/json");
  });

  it("maps non-OK responses to KioskApiError", async () => {
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

  it("normalizes proxy URL construction when path omits leading slash", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ range_id: "r1", name: "Rifle-Pistol", is_open: true, lanes: [] }),
    });

    global.fetch = fetchMock as unknown as typeof fetch;

    await fetchKioskJson("v1/kiosk/range/lanes");

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/kiosk/proxy/v1/kiosk/range/lanes");
  });

  it("maps timed-out requests to a timeout kiosk error", async () => {
    jest.useFakeTimers();
    try {
      const fetchMock = jest.fn().mockImplementation((_: string, init?: RequestInit) =>
        new Promise((_, reject) => {
          const signal = init?.signal;
          signal?.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted.", "AbortError"));
          });
        }));

      global.fetch = fetchMock as unknown as typeof fetch;

      const request = fetchKioskJson("/v1/kiosk/range/lanes", { timeoutMs: 1000 });
      jest.advanceTimersByTime(1000);

      await expect(request).rejects.toMatchObject({
        status: 504,
        message: "Kiosk request timed out. Please try again.",
      });
    } finally {
      jest.useRealTimers();
    }
  });

  it("honors an already-aborted caller signal before starting the request", async () => {
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
