"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Hub } from "aws-amplify/utils";
import { getCurrentUser } from "aws-amplify/auth";

// Cognito redirects here after a successful social login with the auth code in
// the URL. aws-amplify exchanges the code for tokens automatically; this page
// waits for the signedIn Hub event and then navigates to the dashboard.
export default function AuthCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    const unsubscribe = Hub.listen("auth", ({ payload }) => {
      if (payload.event === "signedIn") {
        unsubscribe();
        router.replace("/portal/dashboard");
      }
    });

    // If already signed in (e.g. page refresh after a completed exchange),
    // navigate immediately without waiting for the Hub event.
    getCurrentUser()
      .then(() => {
        unsubscribe();
        router.replace("/portal/dashboard");
      })
      .catch(() => {
        // Not signed in yet — Amplify is still exchanging the auth code.
        // The Hub listener above will fire once the exchange completes.
      });

    return unsubscribe;
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50">
      <p className="text-gray-500 text-sm">Signing in…</p>
    </main>
  );
}
