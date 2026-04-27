import { NextResponse } from "next/server";
import { KIOSK_DEVICE_TOKEN_COOKIE } from "@/lib/kioskSession";

interface KioskSessionBody {
  deviceToken?: string;
}

const MAX_DEVICE_TOKEN_LENGTH = 512;
const DEVICE_TOKEN_PATTERN = /^[A-Za-z0-9._~\-+/=]+$/;
const KIOSK_COOKIE_PATH = "/api/kiosk";

function isSameOriginRequest(request: Request): boolean {
  const requestOrigin = new URL(request.url).origin;
  const originHeader = request.headers.get("origin");
  if (originHeader) {
    if (originHeader !== requestOrigin) {
      return false;
    }
  } else {
    const refererHeader = request.headers.get("referer");
    if (!refererHeader) {
      return false;
    }
    let refererOrigin: string;
    try {
      refererOrigin = new URL(refererHeader).origin;
    } catch {
      return false;
    }
    if (refererOrigin !== requestOrigin) {
      return false;
    }
  }

  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite && fetchSite !== "same-origin" && fetchSite !== "none") {
    return false;
  }

  return true;
}

export async function POST(request: Request): Promise<Response> {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({ error: "Cross-origin requests are not allowed." }, { status: 403 });
  }

  let body: KioskSessionBody;
  try {
    body = (await request.json()) as KioskSessionBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const token = body.deviceToken?.trim();
  if (!token) {
    return NextResponse.json({ error: "deviceToken is required." }, { status: 400 });
  }
  if (token.length > MAX_DEVICE_TOKEN_LENGTH) {
    return NextResponse.json({ error: "deviceToken exceeds maximum length." }, { status: 400 });
  }
  if (!DEVICE_TOKEN_PATTERN.test(token)) {
    return NextResponse.json({ error: "deviceToken format is invalid." }, { status: 400 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: KIOSK_DEVICE_TOKEN_COOKIE,
    value: token,
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: KIOSK_COOKIE_PATH,
    maxAge: 60 * 60 * 24 * 30,
  });
  return response;
}

export async function DELETE(request: Request): Promise<Response> {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({ error: "Cross-origin requests are not allowed." }, { status: 403 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: KIOSK_DEVICE_TOKEN_COOKIE,
    value: "",
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: KIOSK_COOKIE_PATH,
    maxAge: 0,
  });
  return response;
}
