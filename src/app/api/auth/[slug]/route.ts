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

// The Amplify adapter only handles GET internally. For POST sign-out (submitted
// from a form to prevent logout CSRF via cross-site navigation), return a 303
// redirect so the browser performs a normal GET to this same route.
export async function POST(
  request: Request,
  _context: { params: Promise<{ slug: string }> },
): Promise<Response> {
  return Response.redirect(request.url, 303);
}
