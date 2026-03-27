import Link from "next/link";

export default function SiteHeader() {
  return (
    <header className="bg-white border-b border-gray-200">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className="w-12 h-12 bg-green-700 rounded-full flex items-center justify-center shrink-0"
            aria-label="Outdoor Sports Club logo"
          >
            <span className="text-white font-bold text-sm">OSC</span>
          </div>
          <div>
            <div className="font-bold text-green-800 text-lg leading-tight">
              OUTDOOR SPORTS CLUB
            </div>
            <div className="text-xs text-gray-500">
              Conservation · Recreation · Community
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4 text-sm">
          <Link
            href="/contact"
            className="text-green-700 hover:text-green-900 focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
          >
            Questions? Contact us
          </Link>
          <form
            action="/search"
            method="get"
            role="search"
            className="flex items-center gap-1"
          >
            <label htmlFor="site-search" className="sr-only">
              Search
            </label>
            <input
              id="site-search"
              name="q"
              type="search"
              placeholder="Search…"
              className="border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-green-600"
            />
            <button
              type="submit"
              className="text-xs text-gray-500 hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
            >
              Go
            </button>
          </form>
        </div>
      </div>
    </header>
  );
}
