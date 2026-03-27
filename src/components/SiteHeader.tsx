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
            <span className="text-white text-sm font-bold tracking-tight">
              OSC
            </span>
          </div>
          <div>
            <p className="text-green-800 font-bold text-base leading-tight">
              OUTDOOR SPORTS CLUB
            </p>
            <p className="text-gray-500 text-xs">
              Conservation · Recreation · Community
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <Link
            href="/contact"
            className="text-green-700 text-sm hover:text-green-900 focus:outline-none focus:ring-2 focus:ring-green-600 rounded"
          >
            Questions? Contact the chapter
          </Link>
          <form action="/search" method="get" role="search">
            <label htmlFor="site-search" className="sr-only">
              Search
            </label>
            <input
              id="site-search"
              name="q"
              type="search"
              placeholder="Search…"
              className="border border-gray-300 rounded px-3 py-1 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-green-600 w-40"
            />
          </form>
        </div>
      </div>
    </header>
  );
}
