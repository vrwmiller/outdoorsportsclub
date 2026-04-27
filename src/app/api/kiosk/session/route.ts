import { NextResponse } from "next/server";
import { KIOSK_DEVICE_TOKEN_COOKIE } from "@/lib/kioskSession";

interface KioskSessionBody {
  deviceToken?: string;
}

export async function POST(request: Request): Promise<Response> {
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

  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: KIOSK_DEVICE_TOKEN_COOKIE,
    value: token,
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  return response;
}

export async function DELETE(): Promise<Response> {
  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: KIOSK_DEVICE_TOKEN_COOKIE,
    value: "",
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  return response;
}
