import Link from "next/link";
import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { getCurrentUser, fetchAuthSession } from "aws-amplify/auth/server";
import type { MemberProfile } from "@/types/api";
import { getRunWithAmplifyServerContext } from "@/lib/amplifyServerUtils";

async function loadProfile(): Promise<{ profile: MemberProfile | null; error: string | null }> {
  const runWithAmplifyServerContext = getRunWithAmplifyServerContext();
  if (!runWithAmplifyServerContext) {
    return { profile: null, error: "Auth is not configured. Contact an administrator." };
  }

  let idToken: string | null = null;

  try {
    await runWithAmplifyServerContext({
      nextServerContext: { cookies },
      operation: (contextSpec) => getCurrentUser(contextSpec),
    });

    const session = await runWithAmplifyServerContext({
      nextServerContext: { cookies },
      operation: (contextSpec) => fetchAuthSession(contextSpec),
    });

    idToken = session.tokens?.idToken?.toString() ?? null;
  } catch {
    redirect("/");
  }

  if (!idToken) {
    redirect("/");
  }

  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!apiBase) {
    return { profile: null, error: "API base URL is not configured." };
  }

  try {
    const res = await fetch(`${apiBase}/v1/members/me`, {
      headers: { Authorization: `Bearer ${idToken}` },
      cache: "no-store",
    });

    if (!res.ok) {
      return {
        profile: null,
        error: `Failed to load profile (${res.status}). Please try again.`,
      };
    }

    return { profile: (await res.json()) as MemberProfile, error: null };
  } catch {
    return { profile: null, error: "Could not load your profile. Please try again." };
  }
}

export default async function DashboardPage() {
  const { profile, error } = await loadProfile();

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
      <div className="bg-white rounded-2xl shadow-md p-8 max-w-md w-full">
        <h1 className="text-2xl font-bold text-gray-800 mb-6">Dashboard</h1>

        {error ? (
          <p className="text-red-600 text-sm mb-6" role="alert">
            {error}
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
              <dd className="text-gray-800 text-base font-medium">{profile.dues_paid_until ?? "—"}</dd>
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
          <form action="/api/auth/sign-out" method="POST" className="w-full">
            <button
              type="submit"
              className="block w-full text-center bg-gray-100 hover:bg-gray-200 text-gray-900 font-semibold py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-600 transition-colors"
            >
              Sign out
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
