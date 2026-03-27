import Link from "next/link";
import LoginButton from "@/components/LoginButton";
import WeatherWidget from "@/components/WeatherWidget";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";

export default function HomePage() {
  return (
    <div className="bg-gray-50 min-h-screen flex flex-col">
      <SiteHeader />
      <SiteNav />

      <div className="max-w-6xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-6 w-full">
        {/* ── Main column ─────────────────────────────────────────── */}
        <main>
          {/* Status banner */}
          <div className="bg-green-100 border border-green-300 rounded-lg p-4 mb-6 flex items-center gap-3">
            <span className="text-green-800 font-bold text-base">
              Chapter Operating Status:
            </span>
            <span className="bg-green-700 text-white px-3 py-1 rounded-full text-sm font-bold">
              OPEN
            </span>
            <span className="text-green-700 text-sm ml-2">
              Check the{" "}
              <Link
                href="/calendar"
                className="underline focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
              >
                chapter calendar
              </Link>{" "}
              for current hours and closures.
            </span>
          </div>

          {/* Changes / Cancellations / Closures */}
          <section className="mb-6">
            <h2 className="text-xl font-bold text-green-800 border-b-2 border-green-700 pb-1 mb-3">
              Changes / Cancellations / Closures
            </h2>
            <ul className="list-disc list-inside space-y-1 text-gray-700 text-sm">
              <li>No current closures or cancellations.</li>
            </ul>
          </section>

          {/* Announcements */}
          <section className="mb-6">
            <h2 className="text-xl font-bold text-green-800 border-b-2 border-green-700 pb-1 mb-3">
              Announcements
            </h2>
            <ul className="list-disc list-inside space-y-1 text-gray-700 text-sm">
              <li>Check back for upcoming events and announcements.</li>
              <li>
                Chapter meetings: 1st Tuesday (Board) and 3rd Tuesday (General
                Membership) at 7:30 p.m.
              </li>
            </ul>
          </section>

          {/* Membership */}
          <section className="mb-6">
            <h2 className="text-xl font-bold text-green-800 border-b-2 border-green-700 pb-1 mb-3">
              Membership
            </h2>
            <ul className="list-disc list-inside space-y-1 text-gray-700 text-sm">
              <li>2026 Membership Renewal period is now open.</li>
              <li>Contact the membership office for renewal information.</li>
              <li>
                New Member Orientation — see the Membership page for details.
              </li>
            </ul>
          </section>

          {/* Chapter Information */}
          <section className="mb-6">
            <h2 className="text-xl font-bold text-green-800 border-b-2 border-green-700 pb-1 mb-3">
              Chapter Information
            </h2>
            <ul className="list-disc list-inside space-y-1 text-gray-700 text-sm">
              <li>
                All members must display their range badge when accessing all
                chapter ranges.
              </li>
              <li>Chapter speed limit: 10 MPH on all property roads.</li>
              <li>
                Always check the{" "}
                <Link
                  href="/calendar"
                  className="text-green-700 underline focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
                >
                  chapter calendar
                </Link>{" "}
                for up-to-date events and closures.
              </li>
              <li>Chapter Campus Map — available at the main office.</li>
            </ul>
          </section>
        </main>

        {/* ── Sidebar ──────────────────────────────────────────────── */}
        <aside className="flex flex-col gap-4">
          <WeatherWidget />

          {/* Member Login */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 flex flex-col items-center gap-3">
            <h3 className="font-bold text-gray-800">Member Login</h3>
            <LoginButton />
            <Link
              href="/admin"
              className="text-gray-500 text-sm hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
            >
              Admin login
            </Link>
          </div>

          {/* Our Mission */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <h3 className="font-bold text-green-800 mb-2">Our Mission</h3>
            <p className="text-gray-700 text-sm italic">
              To conserve, restore, and promote the sustainable use and
              enjoyment of our natural resources, including soil, air, woods,
              waters, and wildlife.
            </p>
          </div>

          {/* Quick Links */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <h3 className="font-bold text-green-800 mb-2">Quick Links</h3>
            <ul className="space-y-1 text-sm">
              <li>
                <Link
                  href="/calendar"
                  className="text-green-700 hover:underline focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
                >
                  Chapter Calendar
                </Link>
              </li>
              <li>
                <Link
                  href="/about"
                  className="text-green-700 hover:underline focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
                >
                  About the Club
                </Link>
              </li>
              <li>
                <Link
                  href="/contact"
                  className="text-green-700 hover:underline focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
                >
                  Contact Us
                </Link>
              </li>
            </ul>
          </div>
        </aside>
      </div>

      <footer className="bg-green-900 text-white mt-8">
        <div className="max-w-6xl mx-auto px-4 py-4 text-sm text-center text-green-200">
          © 2026 Outdoor Sports Club. All rights reserved.
          <a
            href="https://www.facebook.com"
            className="ml-4 hover:text-white focus:outline-none focus:ring-2 focus:ring-white rounded"
          >
            Facebook
          </a>
        </div>
      </footer>
    </div>
  );
}
