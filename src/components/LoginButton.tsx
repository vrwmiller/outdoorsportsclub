"use client";

import { signInWithRedirect } from "aws-amplify/auth";

export default function LoginButton() {
  return (
    <button
      onClick={() => signInWithRedirect()}
      className="w-full bg-green-700 hover:bg-green-800 text-white font-semibold py-3 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-600 transition-colors"
    >
      Member Login
    </button>
  );
}
