"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export default function AuthCallbackPage() {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const errorCode = params.get("error");
    if (errorCode) {
      setError("Sign-in failed. Please try again.");
      return;
    }

    const query = params.toString();
    const destination = query
      ? `/api/auth/sign-in-callback?${query}`
      : "/api/auth/sign-in-callback";
    window.location.replace(destination);
  }, []);

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
