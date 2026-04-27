import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { KIOSK_DEVICE_TOKEN_COOKIE, getKioskApiBaseUrl } from "@/lib/kioskSession";

const DEVICE_TOKEN_HEADER = "x-device-token";
const KIOSK_ROUTE_PREFIX = ["v1", "kiosk"];

function isAllowedKioskPath(pathSegments: string[]): boolean {
  if (pathSegments.length < KIOSK_ROUTE_PREFIX.length) {
    return false;
  }

  return KIOSK_ROUTE_PREFIX.every((segment, index) => pathSegments[index] === segment);
}

function buildUpstreamUrl(pathSegments: string[]): string {
  const encodedPath = pathSegments.map((segment) => encodeURIComponent(segment)).join("/");
  return `${getKioskApiBaseUrl()}/${encodedPath}`;
}

export async function GET(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const token = (await cookies()).get(KIOSK_DEVICE_TOKEN_COOKIE)?.value;
  if (!token) {
    return NextResponse.json(
      { error: "Forbidden" },
      { status: 403 },
    );
  }

  const { path } = await context.params;
  if (!path || path.length === 0) {
    return NextResponse.json({ error: "Proxy path is required." }, { status: 400 });
  }
  if (!isAllowedKioskPath(path)) {
    return NextResponse.json({ error: "Proxy path is not allowed." }, { status: 403 });
  }

  let upstreamUrl: URL;
  try {
    upstreamUrl = new URL(buildUpstreamUrl(path));
  } catch {
    return NextResponse.json(
      { error: "Kiosk API base URL is not configured." },
      { status: 500 },
    );
  }
  const requestUrl = new URL(request.url);
  upstreamUrl.search = requestUrl.search;

  const upstreamHeaders = new Headers({
    Accept: "application/json",
    [DEVICE_TOKEN_HEADER]: token,
  });

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(upstreamUrl.toString(), {
      method: "GET",
      headers: upstreamHeaders,
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { error: "Kiosk upstream request failed." },
      { status: 502 },
    );
  }

  const contentType = upstreamResponse.headers.get("content-type") ?? "application/json";
  const body = await upstreamResponse.text();

  return new Response(body, {
    status: upstreamResponse.status,
    headers: {
      "content-type": contentType,
    },
  });
}
