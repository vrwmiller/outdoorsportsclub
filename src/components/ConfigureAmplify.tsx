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

function requireEnv(value: string | undefined, name: string): string {
  if (!value) {
    throw new Error(
      `Missing required environment variable "${name}" for Amplify Auth configuration.`,
    );
  }
  return value;
}

function resolveRedirect(value: string | undefined, fallbackPath: string, name: string): string {
  if (value) {
    return value;
  }
  if (typeof window !== "undefined") {
    return `${window.location.origin}${fallbackPath}`;
  }
  throw new Error(
    `Missing environment variable "${name}" and unable to compute redirect URL during SSR.`,
  );
}

// Called once at module load time — safe to run outside a component.
// The { ssr: true } option enables server-side token refresh in Next.js.
Amplify.configure(
  {
    Auth: {
      Cognito: {
        userPoolId: requireEnv(ENV.userPoolId, "NEXT_PUBLIC_COGNITO_USER_POOL_ID"),
        userPoolClientId: requireEnv(ENV.userPoolClientId, "NEXT_PUBLIC_COGNITO_APP_CLIENT_ID"),
        loginWith: {
          oauth: {
            domain: requireEnv(ENV.domain, "NEXT_PUBLIC_COGNITO_DOMAIN"),
            scopes: ["email", "openid", "profile"],
            redirectSignIn: [
              resolveRedirect(ENV.redirectSignIn, "/auth/callback", "NEXT_PUBLIC_COGNITO_REDIRECT_SIGN_IN"),
            ],
            redirectSignOut: [
              resolveRedirect(ENV.redirectSignOut, "/", "NEXT_PUBLIC_COGNITO_REDIRECT_SIGN_OUT"),
            ],
            responseType: "code",
          },
        },
      },
    },
  },
  { ssr: true },
);

export default function ConfigureAmplify() {
  return null;
}
