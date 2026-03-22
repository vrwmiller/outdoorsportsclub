"use client";

import { Amplify } from "aws-amplify";

// Called once at module load time — safe to run outside a component.
// The { ssr: true } option enables server-side token refresh in Next.js.
Amplify.configure(
  {
    Auth: {
      Cognito: {
        userPoolId: process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID ?? "",
        userPoolClientId: process.env.NEXT_PUBLIC_COGNITO_APP_CLIENT_ID ?? "",
        loginWith: {
          oauth: {
            domain: process.env.NEXT_PUBLIC_COGNITO_DOMAIN ?? "",
            scopes: ["email", "openid", "profile"],
            redirectSignIn: [
              process.env.NEXT_PUBLIC_COGNITO_REDIRECT_SIGN_IN ??
                "http://localhost:3000/auth/callback",
            ],
            redirectSignOut: [
              process.env.NEXT_PUBLIC_COGNITO_REDIRECT_SIGN_OUT ??
                "http://localhost:3000",
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
