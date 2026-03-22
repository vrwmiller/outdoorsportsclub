"use client";

import { useEffect, useState } from "react";
import { getCurrentUser, signOut } from "aws-amplify/auth";
import { useRouter } from "next/navigation";

export default function DashboardPage() {
  const [email, setEmail] = useState<string | null>(null);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    getCurrentUser()
      .then((user) => {
        setEmail(user.signInDetails?.loginId ?? user.userId);
      })
      .catch(() => {
        router.replace("/");
      });
  }, [router]);

  async function handleSignOut() {
    if (isSigningOut) return;
    setSignOutError(null);
    setIsSigningOut(true);
    try {
      await signOut();
      router.replace("/");
    } catch (err) {
      console.error("Sign-out failed", err);
      setSignOutError("Sign-out failed. Please try again.");
      setIsSigningOut(false);
    }
  }

  if (!email) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50">
        <p className="text-gray-500 text-sm">Loading…</p>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
      <div className="bg-white rounded-2xl shadow-md p-8 max-w-md w-full">
        <h1 className="text-2xl font-bold text-gray-800 mb-1">Dashboard</h1>
        <p className="text-gray-500 text-sm mb-6">Coming soon.</p>
        <p className="text-gray-800 text-base mb-6">
          Signed in as <span className="font-medium">{email}</span>
        </p>
        <button
          onClick={handleSignOut}
          disabled={isSigningOut}
          aria-disabled={isSigningOut}
          aria-busy={isSigningOut}
          className="w-full bg-gray-100 hover:bg-gray-200 text-gray-900 font-semibold py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-600 transition-colors disabled:opacity-70 disabled:cursor-not-allowed"
        >
          {isSigningOut ? "Signing out…" : "Sign out"}
        </button>
        {signOutError && (
          <p className="mt-2 text-red-600 text-sm" role="alert">
            {signOutError}
          </p>
        )}
      </div>
    </main>
  );
}
