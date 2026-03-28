"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Hub } from "aws-amplify/utils";

// Cognito redirects here after a successful OAuth login with the auth code in
// the URL. In Amplify v6 the token exchange is triggered lazily by the first
// fetchAuthSession() call — it detects ?code= in the URL and completes the
// PKCE exchange. fetchAuthSession() must be called exactly once; concurrent
// calls deadlock Amplify's internal mutex and the exchange never completes.
export default function AuthCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    // Log PKCE state to diagnose state-mismatch failures
    const clientId = process.env.NEXT_PUBLIC_COGNITO_APP_CLIENT_ID ?? "";
    const storedState = localStorage.getItem(`CognitoIdentityServiceProvider.${clientId}.oauthState`);
    const storedPKCE = localStorage.getItem(`CognitoIdentityServiceProvider.${clientId}.oauthPKCE`);
    const urlState = new URLSearchParams(window.location.search).get("state");
    const code = new URLSearchParams(window.location.search).get("code");
    console.log("[callback] code:", code ? code.slice(0, 8) + "…" : "MISSING");
    console.log("[callback] url state:", urlState);
    console.log("[callback] stored state:", storedState);
    console.log("[callback] state match:", urlState === storedState);
    console.log("[callback] has PKCE verifier:", !!storedPKCE);

    // Listen for Amplify signalled completion as backup
    const hubUnsub = Hub.listen("auth", ({ payload }) => {
      console.log("[hub]", payload.event);
      if (payload.event === "signInWithRedirect" || payload.event === "signedIn") {
        if (!cancelled) router.replace("/portal/dashboard");
      } else if (payload.event === "signInWithRedirect_failure") {
        console.error("[hub] failure");
        if (!cancelled) setError("Sign-in failed. Please try again.");
      }
    });

    // In Amplify v6, fetchAuthSession() is what triggers the OAuth code exchange
    // when ?code= is present in the URL. It must be called exactly once — multiple
    // concurrent calls deadlock the internal mutex. No retry loop.
    async function triggerExchange() {
      try {
        console.log("[callback] calling fetchAuthSession() to trigger exchange…");
        const { fetchAuthSession } = await import("aws-amplify/auth");
        const session = await fetchAuthSession();
        console.log("[callback] fetchAuthSession resolved, tokens:", !!session.tokens);
        if (session.tokens?.idToken) {
          if (!cancelled) router.replace("/portal/dashboard");
        } else {
          if (!cancelled) setError("Sign-in failed — no tokens returned. Please try again.");
        }
      } catch (err) {
        console.error("[callback] fetchAuthSession error:", err);
        if (!cancelled) setError("Sign-in failed. Please try again.");
      }
    }

    triggerExchange();

    const timeoutId = setTimeout(() => {
      if (!cancelled) {
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
