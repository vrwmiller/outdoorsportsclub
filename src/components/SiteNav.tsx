import Link from "next/link";

interface NavLink {
  label: string;
  href: string;
  hasDropdown?: false;
}

interface NavDropdown {
  label: string;
  hasDropdown: true;
}

type NavItem = NavLink | NavDropdown;

const NAV_ITEMS: NavItem[] = [
  { label: "HOME", href: "/" },
  { label: "CALENDAR", href: "/calendar" },
  { label: "INFORMATION", hasDropdown: true },
  { label: "RANGES", hasDropdown: true },
  { label: "RESOURCES", hasDropdown: true },
  { label: "CONSERVATION", hasDropdown: true },
  { label: "YOUTH", hasDropdown: true },
  { label: "ABOUT THE CLUB", href: "/about" },
];

const linkClass =
  "block px-4 py-3 text-sm font-semibold tracking-wide hover:bg-green-800 transition-colors whitespace-nowrap";
const activeClass =
  "block px-4 py-3 text-sm font-semibold tracking-wide bg-green-800 hover:bg-green-800 transition-colors whitespace-nowrap";

export default function SiteNav() {
  return (
    <nav className="bg-green-900 text-white" aria-label="Main navigation">
      <div className="max-w-6xl mx-auto px-4">
        <ul className="flex flex-wrap">
          {NAV_ITEMS.map((item) => (
            <li key={item.label}>
              {item.hasDropdown ? (
                <button
                  type="button"
                  disabled
                  className={linkClass + " cursor-default opacity-70"}
                >
                  {item.label} ▾
                </button>
              ) : (
                <Link
                  href={item.href}
                  className={item.href === "/" ? activeClass : linkClass}
                >
                  {item.label}
                </Link>
              )}
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
