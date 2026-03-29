import { NextRequest } from "next/server";
import { getCreateAuthRouteHandlers } from "@/lib/amplifyServerUtils";

async function handleAuthRequest(
  request: Request,
  context: { params: Promise<{ slug: string }> },
): Promise<Response> {
  const createAuthRouteHandlers = getCreateAuthRouteHandlers();
  if (!createAuthRouteHandlers) {
    return Response.json(
      {
        error:
          "Amplify Auth is not configured. Ensure NEXT_PUBLIC_COGNITO_* is set and either NEXT_PUBLIC_COGNITO_REDIRECT_SIGN_IN/OUT or AMPLIFY_APP_ORIGIN are configured.",
      },
      { status: 500 },
    );
  }

  const handler = createAuthRouteHandlers({
    redirectOnSignInComplete: "/portal/dashboard",
    redirectOnSignOutComplete: "/",
  });

  return handler(request, context);
}

export async function GET(
  request: Request,
  context: { params: Promise<{ slug: string }> },
): Promise<Response> {
  const { slug } = await context.params;
  if (slug === "sign-out") {
    return new Response("Method Not Allowed", { status: 405, headers: { Allow: "POST" } });
  }
  return handleAuthRequest(request, context);
}

export async function POST(
  request: Request,
  context: { params: Promise<{ slug: string }> },
): Promise<Response> {
  const { slug } = await context.params;
  if (slug !== "sign-out") {
    return new Response("Method Not Allowed", { status: 405, headers: { Allow: "GET" } });
  }
  const getRequest = new NextRequest(request.url, { method: "GET", headers: request.headers });
  return handleAuthRequest(getRequest, context);
}
