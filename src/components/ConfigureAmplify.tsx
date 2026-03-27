"use client";

import { Amplify } from "aws-amplify";

// Next.js only statically inlines process.env.NEXT_PUBLIC_* when the property
// name is a literal at the call site. Dynamic access (process.env[name]) is
// never replaced in the client bundle — the values are undefined at runtime
// even though they were set at build time. All NEXT_PUBLIC_* reads must use
// static literal property access so the bundler can substitute the values.
const ENV = {
  userPoolId: process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID,
  userPoolClientId: process.env.NEXT_PUBLIC_COGNITO_APP_CLIENT_ID,
  domain: process.env.NEXT_PUBLIC_COGNITO_DOMAIN,
  redirectSignIn: process.env.NEXT_PUBLIC_COGNITO_REDIRECT_SIGN_IN,
  redirectSignOut: process.env.NEXT_PUBLIC_COGNITO_REDIRECT_SIGN_OUT,
};

// If the Cognito stack has not been provisioned yet (local dev before infra is
// deployed), skip Amplify configuration entirely rather than crashing the page.
// Login will be non-functional but the rest of the UI will render normally.
// Extract required fields to local consts so TypeScript can narrow their types
// without assertions — narrowing through an intermediate boolean is unreliable.
const userPoolId = ENV.userPoolId;
const userPoolClientId = ENV.userPoolClientId;
const cognitoDomain = ENV.domain;

if (!userPoolId || !userPoolClientId || !cognitoDomain) {
  if (process.env.NODE_ENV === "production") {
    console.error(
      "[ConfigureAmplify] Cognito env vars not set in production — Amplify Auth is disabled. " +
        "Set NEXT_PUBLIC_COGNITO_* in the deployment environment.",
    );
  } else {
    console.warn(
      "[ConfigureAmplify] Cognito env vars not set — Amplify Auth is disabled. " +
        "Set NEXT_PUBLIC_COGNITO_* in .env.local to enable login.",
    );
  }
} else {
  // Redirect URLs require window.location.origin when env vars are not explicitly set.
  // Use null (not "") as the SSR fallback so we can detect and skip misconfigured calls.
  const redirectSignIn =
    ENV.redirectSignIn ??
    (typeof window !== "undefined" ? `${window.location.origin}/auth/callback` : null);
  const redirectSignOut =
    ENV.redirectSignOut ??
    (typeof window !== "undefined" ? `${window.location.origin}/` : null);

  if (!redirectSignIn || !redirectSignOut) {
    // SSR context: redirect URLs cannot be computed without window.location.origin
    // and NEXT_PUBLIC_COGNITO_REDIRECT_* env vars are not set. Skip Amplify.configure
    // here — the browser will configure Amplify when this module re-evaluates client-side.
    if (process.env.NODE_ENV === "production") {
      console.error(
        "[ConfigureAmplify] NEXT_PUBLIC_COGNITO_REDIRECT_* env vars are not set. " +
          "Set them in the deployment environment — login will fail without explicit redirect URLs.",
      );
    }
  } else {
    // Called once at module load time in the browser — safe to run outside a component.
    // The { ssr: true } option configures Amplify to use cookies instead of localStorage
    // so that Server Components and middleware can read the auth session server-side.
    Amplify.configure(
      {
        Auth: {
          Cognito: {
            userPoolId,
            userPoolClientId,
            loginWith: {
              oauth: {
                domain: cognitoDomain,
                scopes: ["email", "openid", "profile"],
                redirectSignIn: [redirectSignIn],
                redirectSignOut: [redirectSignOut],
                responseType: "code",
              },
            },
          },
        },
      },
      { ssr: true },
    );
  }
}

export default function ConfigureAmplify() {
  return null;
}
