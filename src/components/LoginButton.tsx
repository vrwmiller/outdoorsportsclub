"use client";

import { useState } from "react";
import { signInWithRedirect } from "aws-amplify/auth";

export default function LoginButton() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    if (isSubmitting) return;
    setError(null);
    setIsSubmitting(true);
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
