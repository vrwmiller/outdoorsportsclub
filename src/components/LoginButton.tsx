"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { signInWithRedirect, getCurrentUser } from "aws-amplify/auth";

export default function LoginButton() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function handleClick() {
    if (isSubmitting) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await getCurrentUser();
      // Already signed in — go straight to the dashboard.
      router.push("/portal/dashboard");
      return;
    } catch {
      // Not signed in — proceed with the hosted UI redirect.
    }
    try {
      await signInWithRedirect();
    } catch (err) {
      console.error("Failed to start login redirect", err);
      setError("We could not start the login process. Please try again.");
      setIsSubmitting(false);
    }
  }

  return (
    <>
      <button
        onClick={handleClick}
        disabled={isSubmitting}
        aria-disabled={isSubmitting}
        aria-busy={isSubmitting}
        className="w-full bg-green-700 hover:bg-green-800 text-white font-semibold py-3 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-600 transition-colors disabled:opacity-70 disabled:cursor-not-allowed"
      >
        {isSubmitting ? "Starting login…" : "Member Login"}
      </button>
      {error && (
        <p className="mt-2 text-red-600 text-sm" role="alert">
          {error}
        </p>
      )}
    </>
  );
}
