"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Hub } from "aws-amplify/utils";
import { getCurrentUser } from "aws-amplify/auth";

// Cognito redirects here after a successful social login with the auth code in
// the URL. aws-amplify exchanges the code for tokens automatically; this page
// waits for the signedIn Hub event and then navigates to the dashboard.
export default function AuthCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const unsubscribe = Hub.listen("auth", ({ payload }) => {
      if (payload.event === "signedIn") {
        unsubscribe();
        router.replace("/portal/dashboard");
      } else if (payload.event === "signInWithRedirect_failure") {
        unsubscribe();
        console.error("OAuth sign-in failed", payload.data);
        setError("Sign-in failed. Please try again.");
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
