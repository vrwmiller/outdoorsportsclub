import { getCreateAuthRouteHandlers } from "@/lib/amplifyServerUtils";

export async function GET(request: Request, context: { params: Promise<{ slug: string }> }) {
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
