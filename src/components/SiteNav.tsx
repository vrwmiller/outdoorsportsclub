import Link from "next/link";

interface NavItem {
  label: string;
  href: string;
  hasDropdown?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "HOME", href: "/" },
  { label: "CALENDAR", href: "/calendar" },
  { label: "INFORMATION", href: "#", hasDropdown: true },
  { label: "RANGES", href: "#", hasDropdown: true },
  { label: "RESOURCES", href: "#", hasDropdown: true },
  { label: "CONSERVATION", href: "#", hasDropdown: true },
  { label: "YOUTH", href: "#", hasDropdown: true },
  { label: "ABOUT THE CLUB", href: "/about" },
];

export default function SiteNav() {
  return (
    <nav className="bg-green-900 text-white" aria-label="Main navigation">
      <div className="max-w-6xl mx-auto px-4">
        <ul className="flex flex-wrap">
          {NAV_ITEMS.map((item) => (
            <li key={item.label}>
              <Link
                href={item.href}
                className={
                  item.href === "/"
                    ? "block px-4 py-3 text-sm font-semibold tracking-wide bg-green-800 hover:bg-green-800 transition-colors whitespace-nowrap"
                    : "block px-4 py-3 text-sm font-semibold tracking-wide hover:bg-green-800 transition-colors whitespace-nowrap"
                }
              >
                {item.label}
                {item.hasDropdown ? " ▾" : ""}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
