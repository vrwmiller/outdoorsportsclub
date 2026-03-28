"use client";

import { useState } from "react";
import { getCurrentUser, updatePassword, signOut } from "aws-amplify/auth";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect } from "react";

export default function SettingsPage() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    getCurrentUser().catch(() => {
      router.replace("/");
    });
  }, [router]);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    if (newPassword !== confirmPassword) {
      setError("New passwords do not match.");
      return;
    }

    if (newPassword.length < 12) {
      setError("New password must be at least 12 characters.");
      return;
    }

    setIsSubmitting(true);
    try {
      await updatePassword({ oldPassword: currentPassword, newPassword });
      await signOut();
      router.replace("/");
    } catch (err: unknown) {
      console.error("Password change failed", err);
      let message = "Password change failed. Please try again.";
      if (err instanceof Error) {
        const name = (err as { name?: string }).name ?? "";
        if (name === "NotAuthorizedException") {
          message = "Current password is incorrect.";
        } else if (name === "InvalidPasswordException" || name === "InvalidParameterException") {
          message = "New password does not meet the requirements. Use at least 12 characters with uppercase, lowercase, and a number.";
        } else if (name === "LimitExceededException") {
          message = "Too many attempts. Please wait a few minutes and try again.";
        }
      }
      setError(message);
      setIsSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
      <div className="bg-white rounded-2xl shadow-md p-8 max-w-md w-full">
        <h1 className="text-2xl font-bold text-gray-800 mb-6">Settings</h1>

        <h2 className="text-base font-semibold text-gray-800 mb-4">Change password</h2>

        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          <div>
            <label
              htmlFor="currentPassword"
              className="block text-gray-500 text-sm mb-1"
            >
              Current password
            </label>
            <input
              id="currentPassword"
              type="password"
              autoComplete="current-password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              disabled={isSubmitting}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-gray-800 text-base focus:outline-none focus:ring-2 focus:ring-green-600 disabled:opacity-70"
            />
          </div>

          <div>
            <label
              htmlFor="newPassword"
              className="block text-gray-500 text-sm mb-1"
            >
              New password
            </label>
            <input
              id="newPassword"
              type="password"
              autoComplete="new-password"
              required
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              disabled={isSubmitting}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-gray-800 text-base focus:outline-none focus:ring-2 focus:ring-green-600 disabled:opacity-70"
            />
          </div>

          <div>
            <label
              htmlFor="confirmPassword"
              className="block text-gray-500 text-sm mb-1"
            >
              Confirm new password
            </label>
            <input
              id="confirmPassword"
              type="password"
              autoComplete="new-password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={isSubmitting}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-gray-800 text-base focus:outline-none focus:ring-2 focus:ring-green-600 disabled:opacity-70"
            />
            {confirmPassword && newPassword !== confirmPassword && (
              <p className="mt-1 text-red-600 text-sm" role="alert">
                Passwords do not match.
              </p>
            )}
          </div>

          {error && (
            <p className="text-red-600 text-sm" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={isSubmitting || !currentPassword || !newPassword || !confirmPassword}
            aria-disabled={isSubmitting || !currentPassword || !newPassword || !confirmPassword}
            aria-busy={isSubmitting}
            className="w-full bg-green-700 hover:bg-green-800 text-white font-semibold py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-600 transition-colors disabled:opacity-70 disabled:cursor-not-allowed"
          >
            {isSubmitting ? "Updating…" : "Update password"}
          </button>
        </form>

        <div className="mt-6 border-t border-gray-100 pt-4">
          <Link
            href="/portal/dashboard"
            className="text-sm text-gray-500 hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
          >
            &larr; Back to dashboard
          </Link>
        </div>
      </div>
    </main>
  );
}
