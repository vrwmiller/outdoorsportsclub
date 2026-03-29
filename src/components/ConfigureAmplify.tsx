"use client";

import { Amplify } from "aws-amplify";
import { getClientAmplifyConfig } from "@/config/amplifyAuth";

// Next.js only statically inlines process.env.NEXT_PUBLIC_* when the property
// name is a literal at the call site. Dynamic access (process.env[name]) is
// never replaced in the client bundle — the values are undefined at runtime
// even though they were set at build time. All NEXT_PUBLIC_* reads must use
// static literal property access so the bundler can substitute the values.
const config = getClientAmplifyConfig();

if (!config) {
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
  // With { ssr: true }, OAuth code exchange happens in route handlers and
  // tokens are stored in httpOnly cookies instead of localStorage.
  Amplify.configure(config, { ssr: true });
}

export default function ConfigureAmplify() {
  return null;
}
