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

export const GET = handleAuthRequest;

// Sign-out is exposed as POST so the UI can use a form submission rather than
// a plain link, preventing logout CSRF via cross-site navigation.
export const POST = handleAuthRequest;
