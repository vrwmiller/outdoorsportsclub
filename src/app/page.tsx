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
          <div className="bg-green-100 border border-green-300 rounded-lg p-4 mb-6">
            <span className="text-green-800 font-bold text-lg">
              Chapter Operating Status:
            </span>
            <span className="bg-green-700 text-white px-3 py-1 rounded-full text-sm font-bold ml-2">
              OPEN
            </span>
            <p className="text-green-700 text-sm mt-2">
              Check the{" "}
              <Link
                href="/calendar"
                className="underline hover:text-green-900 focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
              >
                calendar
              </Link>{" "}
              for scheduled range hours and events.
            </p>
          </div>

          {/* Changes / Cancellations / Closures */}
          <section className="mb-6">
            <h2 className="text-xl font-bold text-green-800 border-b-2 border-green-700 pb-1 mb-3">
              Changes / Cancellations / Closures:
            </h2>
            <ul className="list-disc list-inside space-y-1 text-gray-700 text-sm">
              <li>No current closures.</li>
            </ul>
          </section>

          {/* Announcements */}
          <section className="mb-6">
            <h2 className="text-xl font-bold text-green-800 border-b-2 border-green-700 pb-1 mb-3">
              Announcements:
            </h2>
            <ul className="list-disc list-inside space-y-1 text-gray-700 text-sm">
              <li>Check back for upcoming events and club news.</li>
            </ul>
          </section>

          {/* Membership */}
          <section className="mb-6">
            <h2 className="text-xl font-bold text-green-800 border-b-2 border-green-700 pb-1 mb-3">
              Membership:
            </h2>
            <ul className="list-disc list-inside space-y-1 text-gray-700 text-sm">
              <li>
                Annual dues renewals are processed through the Member Portal.
              </li>
              <li>
                New members must complete a safety orientation before range
                access is granted.
              </li>
              <li>
                Guest passes are available — members may sponsor up to two
                guests per visit.
              </li>
              <li>
                Contact the membership committee with any questions about your
                account.
              </li>
            </ul>
          </section>

          {/* Chapter Information */}
          <section className="mb-6">
            <h2 className="text-xl font-bold text-green-800 border-b-2 border-green-700 pb-1 mb-3">
              Chapter Information:
            </h2>
            <ul className="list-disc list-inside space-y-1 text-gray-700 text-sm">
              <li>
                General meetings are held monthly — see the calendar for dates
                and times.
              </li>
              <li>
                Range safety rules and operating procedures are posted at each
                range entrance.
              </li>
              <li>
                Training courses and certification programs are offered
                throughout the year.
              </li>
              <li>
                Conservation projects and volunteer opportunities are listed on
                the calendar.
              </li>
            </ul>
          </section>
        </main>

        {/* ── Sidebar ──────────────────────────────────────────────── */}
        <aside className="flex flex-col gap-4">
          {/* Weather */}
          <WeatherWidget />

          {/* Member login */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 flex flex-col items-center gap-3">
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
            <h3 className="text-green-800 font-bold text-sm mb-2 uppercase tracking-wide">
              Our Mission
            </h3>
            <p className="text-gray-700 text-sm leading-relaxed">
              To conserve, restore, and promote the sustainable use and
              enjoyment of our natural resources, including soil, air, woods,
              waters, and wildlife.
            </p>
          </div>

          {/* Quick Links */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <h3 className="text-green-800 font-bold text-sm mb-2 uppercase tracking-wide">
              Quick Links
            </h3>
            <ul className="space-y-2">
              <li>
                <Link
                  href="/calendar"
                  className="text-green-700 text-sm hover:text-green-900 hover:underline focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
                >
                  Calendar
                </Link>
              </li>
              <li>
                <Link
                  href="/about"
                  className="text-green-700 text-sm hover:text-green-900 hover:underline focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
                >
                  About
                </Link>
              </li>
              <li>
                <Link
                  href="/contact"
                  className="text-green-700 text-sm hover:text-green-900 hover:underline focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
                >
                  Contact
                </Link>
              </li>
            </ul>
          </div>
        </aside>
      </div>

      <footer className="bg-green-900 text-white mt-8">
        <div className="max-w-6xl mx-auto px-4 py-6 flex flex-col sm:flex-row items-center justify-between gap-3">
          <p className="text-sm">
            © 2026 Outdoor Sports Club. All rights reserved.
          </p>
          <a
            href="#"
            aria-label="Outdoor Sports Club on Facebook"
            className="text-white text-sm hover:underline focus:outline-none focus:ring-2 focus:ring-white rounded"
          >
            Facebook
          </a>
        </div>
      </footer>
    </div>
  );
}
