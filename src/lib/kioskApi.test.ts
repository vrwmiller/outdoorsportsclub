import {
  KioskApiError,
  fetchKioskJson,
  getKioskRangeLanes,
} from "@/lib/kioskApi";

describe("kioskApi", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetAllMocks();
    process.env = { ...originalEnv };
  });

  afterAll(() => {
    process.env = originalEnv;
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
      status: 401,
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

    await expect(getKioskRangeLanes()).rejects.toBeInstanceOf(KioskApiError);
    await expect(getKioskRangeLanes()).rejects.toMatchObject({
      status: 403,
      message: "Device token revoked",
    });
  });
});
