"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getCurrentUser, fetchAuthSession, signOut } from "aws-amplify/auth";
import type { MemberProfile } from "@/types/api";

export default function DashboardPage() {
  const [profile, setProfile] = useState<MemberProfile | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    async function loadProfile() {
      try {
        await getCurrentUser();
      } catch {
        router.replace("/");
        return;
      }

      try {
        const session = await fetchAuthSession();
        const idToken = session.tokens?.idToken?.toString();
        if (!idToken) {
          setLoadError("Session expired. Please sign in again.");
          return;
        }

        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_BASE_URL}/v1/members/me`,
          { headers: { Authorization: `Bearer ${idToken}` } }
        );

        if (!res.ok) {
          setLoadError(`Failed to load profile (${res.status}). Please try again.`);
          return;
        }

        setProfile(await res.json());
      } catch (err) {
        console.error("Failed to load member profile", err);
        setLoadError("Could not load your profile. Please try again.");
      }
    }

    loadProfile();
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

  if (!profile && !loadError) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50">
        <p className="text-gray-500 text-sm">Loading…</p>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
      <div className="bg-white rounded-2xl shadow-md p-8 max-w-md w-full">
        <h1 className="text-2xl font-bold text-gray-800 mb-6">Dashboard</h1>

        {loadError ? (
          <p className="text-red-600 text-sm mb-6" role="alert">
            {loadError}
          </p>
        ) : profile ? (
          <dl className="mb-6 space-y-3">
            <div>
              <dt className="text-gray-500 text-sm">Member number</dt>
              <dd className="text-gray-800 text-base font-medium">{profile.member_num}</dd>
            </div>
            <div>
              <dt className="text-gray-500 text-sm">Training level</dt>
              <dd className="text-gray-800 text-base font-medium">{profile.training_level}</dd>
            </div>
            <div>
              <dt className="text-gray-500 text-sm">Dues paid until</dt>
              <dd className="text-gray-800 text-base font-medium">
                {profile.dues_paid_until ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500 text-sm">Annual dues</dt>
              <dd className="text-gray-800 text-base font-medium">
                {profile.annual_dues_cents != null
                  ? `$${(profile.annual_dues_cents / 100).toFixed(2)}`
                  : "—"}
              </dd>
            </div>
          </dl>
        ) : null}
        <div className="space-y-3">
          <Link
            href="/portal/settings"
            className="block w-full text-center bg-gray-100 hover:bg-gray-200 text-gray-900 font-semibold py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-600 transition-colors"
          >
            Settings
          </Link>
          <button
            onClick={handleSignOut}
            disabled={isSigningOut}
            aria-disabled={isSigningOut}
            aria-busy={isSigningOut}
            className="w-full bg-gray-100 hover:bg-gray-200 text-gray-900 font-semibold py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-600 transition-colors disabled:opacity-70 disabled:cursor-not-allowed"
          >
            {isSigningOut ? "Signing out…" : "Sign out"}
          </button>
        </div>
        {signOutError && (
          <p className="mt-2 text-red-600 text-sm" role="alert">
            {signOutError}
          </p>
        )}
      </div>
    </main>
  );
}
