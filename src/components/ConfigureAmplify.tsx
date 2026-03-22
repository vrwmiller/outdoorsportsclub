"use client";

import { Amplify } from "aws-amplify";

function getRequiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Missing required environment variable "${name}" for Amplify Auth configuration.`,
    );
  }
  return value;
}

function getRedirectUrl(envName: string, fallbackPath: string): string {
  const value = process.env[envName];
  if (value) {
    return value;
  }
  if (typeof window !== "undefined") {
    return `${window.location.origin}${fallbackPath}`;
  }
  throw new Error(
    `Missing environment variable "${envName}" and unable to compute redirect URL during SSR.`,
  );
}

// Called once at module load time — safe to run outside a component.
// The { ssr: true } option enables server-side token refresh in Next.js.
Amplify.configure(
  {
    Auth: {
      Cognito: {
        userPoolId: getRequiredEnv("NEXT_PUBLIC_COGNITO_USER_POOL_ID"),
        userPoolClientId: getRequiredEnv("NEXT_PUBLIC_COGNITO_APP_CLIENT_ID"),
        loginWith: {
          oauth: {
            domain: getRequiredEnv("NEXT_PUBLIC_COGNITO_DOMAIN"),
            scopes: ["email", "openid", "profile"],
            redirectSignIn: [
              getRedirectUrl(
                "NEXT_PUBLIC_COGNITO_REDIRECT_SIGN_IN",
                "/auth/callback",
              ),
            ],
            redirectSignOut: [
              getRedirectUrl("NEXT_PUBLIC_COGNITO_REDIRECT_SIGN_OUT", "/"),
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
