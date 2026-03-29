import { createServerRunner } from "@aws-amplify/adapter-nextjs";
import { getServerAmplifyConfig } from "@/config/amplifyAuth";

type ServerRunner = ReturnType<typeof createServerRunner>;

function ensureAmplifyAppOrigin(): void {
  if (process.env.AMPLIFY_APP_ORIGIN) {
    return;
  }

  const redirectSignIn = process.env.NEXT_PUBLIC_COGNITO_REDIRECT_SIGN_IN;
  if (!redirectSignIn) {
    return;
  }

  try {
    process.env.AMPLIFY_APP_ORIGIN = new URL(redirectSignIn).origin;
  } catch {
    // Keep existing behavior when redirectSignIn is invalid.
  }
}

function getServerRunner(): ServerRunner | null {
  ensureAmplifyAppOrigin();

  const config = getServerAmplifyConfig();
  if (!config) {
    return null;
  }

  return createServerRunner({ config });
}

export function getRunWithAmplifyServerContext():
  | ServerRunner["runWithAmplifyServerContext"]
  | null {
  const runner = getServerRunner();
  if (!runner) {
    return null;
  }

  return runner.runWithAmplifyServerContext;
}

export function getCreateAuthRouteHandlers(): ServerRunner["createAuthRouteHandlers"] | null {
  const runner = getServerRunner();
  if (!runner) {
    return null;
  }

  return runner.createAuthRouteHandlers;
}
