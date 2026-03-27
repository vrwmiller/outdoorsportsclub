import Link from "next/link";

interface NavItem {
  label: string;
  href: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: "HOME", href: "/" },
  { label: "CALENDAR", href: "/calendar" },
  { label: "INFORMATION ▾", href: "#" },
  { label: "RANGES ▾", href: "#" },
  { label: "RESOURCES ▾", href: "#" },
  { label: "CONSERVATION ▾", href: "#" },
  { label: "YOUTH ▾", href: "#" },
  { label: "ABOUT THE CLUB", href: "/about" },
];

export default function SiteNav() {
  return (
    <nav className="bg-green-900 text-white" aria-label="Main navigation">
      <div className="max-w-6xl mx-auto px-4">
        <ul className="flex flex-wrap gap-0">
          {NAV_ITEMS.map((item) => (
            <li key={item.label}>
              <Link
                href={item.href}
                className={
                  item.href === "/"
                    ? "block px-4 py-3 text-sm font-semibold tracking-wide bg-green-800 transition-colors"
                    : "block px-4 py-3 text-sm font-semibold tracking-wide hover:bg-green-800 transition-colors"
                }
              >
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
