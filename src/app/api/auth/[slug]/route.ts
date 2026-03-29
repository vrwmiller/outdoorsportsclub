import { getCreateAuthRouteHandlers } from "@/lib/amplifyServerUtils";

export async function GET(request: Request, context: { params: Promise<{ slug: string }> }) {
  const createAuthRouteHandlers = getCreateAuthRouteHandlers();
  if (!createAuthRouteHandlers) {
    return Response.json(
      {
        error:
          "Amplify Auth is not configured. Set NEXT_PUBLIC_COGNITO_* and AMPLIFY_APP_ORIGIN.",
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
