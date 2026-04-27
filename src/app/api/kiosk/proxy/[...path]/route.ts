import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { KIOSK_DEVICE_TOKEN_COOKIE, getKioskApiBaseUrl } from "@/lib/kioskSession";

const DEVICE_TOKEN_HEADER = "x-device-token";

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
      { error: "Kiosk device token is not configured. Pair this kiosk device first." },
      { status: 401 },
    );
  }

  const { path } = await context.params;
  if (!path || path.length === 0) {
    return NextResponse.json({ error: "Proxy path is required." }, { status: 400 });
  }

  const upstreamUrl = new URL(buildUpstreamUrl(path));
  const requestUrl = new URL(request.url);
  upstreamUrl.search = requestUrl.search;

  const upstreamHeaders = new Headers({
    Accept: "application/json",
    [DEVICE_TOKEN_HEADER]: token,
  });

  const upstreamResponse = await fetch(upstreamUrl.toString(), {
    method: "GET",
    headers: upstreamHeaders,
    cache: "no-store",
  });

  const contentType = upstreamResponse.headers.get("content-type") ?? "application/json";
  const body = await upstreamResponse.text();

  return new Response(body, {
    status: upstreamResponse.status,
    headers: {
      "content-type": contentType,
    },
  });
}
