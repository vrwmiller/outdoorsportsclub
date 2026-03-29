import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getCurrentUser } from "aws-amplify/auth/server";
import { getRunWithAmplifyServerContext } from "@/lib/amplifyServerUtils";

export default async function SettingsPage() {
  const runWithAmplifyServerContext = getRunWithAmplifyServerContext();
  if (!runWithAmplifyServerContext) {
    redirect("/");
  }

  let username: string | null = null;
  try {
    const user = await runWithAmplifyServerContext({
      nextServerContext: { cookies },
      operation: (contextSpec: Parameters<typeof getCurrentUser>[0]) => getCurrentUser(contextSpec),
    });
    username = user?.username ?? null;
  } catch {
    redirect("/");
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
      <div className="bg-white rounded-2xl shadow-md p-8 max-w-md w-full">
        <h1 className="text-2xl font-bold text-gray-800 mb-6">Settings</h1>

        <div className="space-y-4">
          <p className="text-gray-800 text-base">
            Signed in as <span className="font-semibold">{username ?? "member"}</span>.
          </p>
          <p className="text-gray-500 text-sm">
            Password changes are managed by your identity provider for this account.
          </p>
          <form action="/api/auth/sign-out" method="POST">
            <button
              type="submit"
              className="inline-flex bg-red-600 hover:bg-red-700 text-white font-semibold py-2 px-4 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-600 transition-colors"
            >
              Sign out
            </button>
          </form>
        </div>

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
