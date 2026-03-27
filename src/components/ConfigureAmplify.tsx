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
const cognitoConfigured =
  ENV.userPoolId &&
  ENV.userPoolClientId &&
  ENV.domain;

if (!cognitoConfigured) {
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
  const redirectSignIn =
    ENV.redirectSignIn ??
    (typeof window !== "undefined" ? `${window.location.origin}/auth/callback` : "");
  const redirectSignOut =
    ENV.redirectSignOut ??
    (typeof window !== "undefined" ? `${window.location.origin}/` : "");

  // Called once at module load time — safe to run outside a component.
  // The { ssr: true } option enables server-side token refresh in Next.js.
  Amplify.configure(
    {
      Auth: {
        Cognito: {
          userPoolId: ENV.userPoolId,
          userPoolClientId: ENV.userPoolClientId,
          loginWith: {
            oauth: {
              domain: ENV.domain,
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

export default function ConfigureAmplify() {
  return null;
}
