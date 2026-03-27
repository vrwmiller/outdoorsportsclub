import Link from "next/link";
import LoginButton from "@/components/LoginButton";
import WeatherWidget from "@/components/WeatherWidget";

export default function HomePage() {
  return (
    <main className="bg-gray-50 min-h-screen flex flex-col items-center justify-center px-4 py-16">
      <div className="w-full max-w-md flex flex-col gap-6">
        <div className="bg-white rounded-2xl shadow-md p-6 text-center">
          <h1 className="text-3xl font-bold text-gray-800 mb-2">
            Outdoor Sports Club
          </h1>
          <p className="text-gray-500 text-sm">
            Your home for outdoor recreation — ranges, training, and community.
          </p>
        </div>

        <WeatherWidget />

        <div className="bg-white rounded-2xl shadow-md p-6 flex flex-col items-center gap-4">
          <LoginButton />
          <Link
            href="/admin"
            className="text-gray-500 text-sm hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
          >
            Admin login
          </Link>
        </div>
      </div>
    </main>
  );
}
