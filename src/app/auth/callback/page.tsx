"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Hub } from "aws-amplify/utils";

// Cognito redirects here after a successful OAuth login with the auth code in
// the URL. In Amplify v6 the token exchange is triggered lazily by the first
// fetchAuthSession() call — it detects ?code= in the URL and completes the
// PKCE exchange. A module-level flag ensures the exchange is attempted exactly
// once per page load — prevents React Strict Mode's synthetic double-mount from
// triggering a second exchange and consuming the one-time-use PKCE code.
let _exchangeStarted = false;

export default function AuthCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (_exchangeStarted) return;
    _exchangeStarted = true;

    let cancelled = false;
    let finished = false;

    // Log PKCE state to diagnose state-mismatch failures (dev only)
    const clientId = process.env.NEXT_PUBLIC_COGNITO_APP_CLIENT_ID ?? "";
    const storedState = localStorage.getItem(`CognitoIdentityServiceProvider.${clientId}.oauthState`);
    const storedPKCE = localStorage.getItem(`CognitoIdentityServiceProvider.${clientId}.oauthPKCE`);
    const urlState = new URLSearchParams(window.location.search).get("state");
    const code = new URLSearchParams(window.location.search).get("code");
    const isDev = process.env.NODE_ENV !== "production";
    if (isDev) {
      console.log("[callback] code:", code ? code.slice(0, 8) + "…" : "MISSING");
      console.log("[callback] url state:", urlState);
      console.log("[callback] stored state:", storedState);
      console.log("[callback] state match:", urlState === storedState);
      console.log("[callback] has PKCE verifier:", !!storedPKCE);
    }

    // Listen for Amplify signalled completion as backup
    const hubUnsub = Hub.listen("auth", ({ payload }) => {
      if (isDev) console.log("[hub]", payload.event);
      if (payload.event === "signInWithRedirect" || payload.event === "signedIn") {
        if (!cancelled && !finished) { finished = true; router.replace("/portal/dashboard"); }
      } else if (payload.event === "signInWithRedirect_failure") {
        console.error("[hub] failure");
        if (!cancelled && !finished) { finished = true; setError("Sign-in failed. Please try again."); }
      }
    });

    // In Amplify v6, fetchAuthSession() is what triggers the OAuth code exchange
    // when ?code= is present in the URL. It must be called exactly once — multiple
    // concurrent calls deadlock the internal mutex. No retry loop.
    async function triggerExchange() {
      try {
        if (isDev) console.log("[callback] calling fetchAuthSession() to trigger exchange…");
        const { fetchAuthSession } = await import("aws-amplify/auth");
        const session = await fetchAuthSession();
        if (isDev) console.log("[callback] fetchAuthSession resolved, tokens:", !!session.tokens);
        if (session.tokens?.idToken) {
          if (!cancelled && !finished) { finished = true; router.replace("/portal/dashboard"); }
        } else {
          if (!cancelled && !finished) { finished = true; setError("Sign-in failed — no tokens returned. Please try again."); }
        }
      } catch (err) {
        console.error("[callback] fetchAuthSession error:", err);
        if (!cancelled && !finished) { finished = true; setError("Sign-in failed. Please try again."); }
      }
    }

    triggerExchange();

    const timeoutId = setTimeout(() => {
      if (!cancelled && !finished) {
        finished = true;
        console.error("[callback] timed out — exchange did not complete after 30s");
        setError("Sign-in timed out. Please try again.");
      }
    }, 30_000);

    return () => {
      cancelled = true;
      hubUnsub();
      clearTimeout(timeoutId);
    };
  }, [router]);

  if (error) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
        <div className="bg-white rounded-2xl shadow-md p-8 max-w-md w-full text-center">
          <p className="text-red-600 text-base mb-4" role="alert">
            {error}
          </p>
          <Link
            href="/"
            className="text-green-700 hover:text-green-800 font-semibold underline text-sm"
          >
            Back to home
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50">
      <p className="text-gray-500 text-sm">Signing in…</p>
    </main>
  );
}
