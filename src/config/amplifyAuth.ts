import type { ResourcesConfig } from "aws-amplify";

const COGNITO_USER_POOL_ID = process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID;
const COGNITO_APP_CLIENT_ID = process.env.NEXT_PUBLIC_COGNITO_APP_CLIENT_ID;
const COGNITO_DOMAIN = process.env.NEXT_PUBLIC_COGNITO_DOMAIN;
const COGNITO_REDIRECT_SIGN_IN = process.env.NEXT_PUBLIC_COGNITO_REDIRECT_SIGN_IN;
const COGNITO_REDIRECT_SIGN_OUT = process.env.NEXT_PUBLIC_COGNITO_REDIRECT_SIGN_OUT;

function buildConfig(origin?: string): ResourcesConfig | null {
  if (!COGNITO_USER_POOL_ID || !COGNITO_APP_CLIENT_ID || !COGNITO_DOMAIN) {
    return null;
  }

  const redirectSignIn = COGNITO_REDIRECT_SIGN_IN ?? (origin ? `${origin}/auth/callback` : null);
  const redirectSignOut = COGNITO_REDIRECT_SIGN_OUT ?? (origin ? `${origin}/` : null);

  if (!redirectSignIn || !redirectSignOut) {
    return null;
  }

  return {
    Auth: {
      Cognito: {
        userPoolId: COGNITO_USER_POOL_ID,
        userPoolClientId: COGNITO_APP_CLIENT_ID,
        loginWith: {
          oauth: {
            domain: COGNITO_DOMAIN,
            scopes: ["email", "openid", "profile", "aws.cognito.signin.user.admin"],
            redirectSignIn: [redirectSignIn],
            redirectSignOut: [redirectSignOut],
            responseType: "code",
          },
        },
      },
    },
  };
}

export function getClientAmplifyConfig(): ResourcesConfig | null {
  if (typeof window === "undefined") {
    return null;
  }

  return buildConfig(window.location.origin);
}

export function getServerAmplifyConfig(): ResourcesConfig | null {
  const origin = process.env.AMPLIFY_APP_ORIGIN;
  return buildConfig(origin);
}
