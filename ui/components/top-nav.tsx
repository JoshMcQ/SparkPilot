"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useInternalAdmin } from "@/lib/use-internal-admin";
import { buildTopNavItems } from "@/lib/top-nav-items";

function _isActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function TopNav() {
  const pathname = usePathname();
  const { isInternalAdmin } = useInternalAdmin();
  const navItems = buildTopNavItems(isInternalAdmin);
  return (
    <nav className="nav" aria-label="Primary">
      {navItems.map((item) => {
        const active = _isActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`nav-link${active ? " active" : ""}`}
            aria-current={active ? "page" : undefined}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
