"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/theme-toggle";
import { appHref } from "@/lib/app-url";

export function LandingNav() {
  const pathname = usePathname();

  return (
    <nav className="landing-nav">
      <Link href="/" className="landing-nav-brand">
        <strong>SparkPilot</strong>
      </Link>
      <div className="landing-nav-links">
        <Link href="/#features" className={pathname === "/" ? "landing-nav-active" : ""}>
          Features
        </Link>
        <Link href="/#integrations" className={pathname === "/" ? "landing-nav-active" : ""}>
          Integrations
        </Link>
        <Link href="/pricing" className={pathname === "/pricing" ? "landing-nav-active" : ""}>
          Pricing
        </Link>
        <Link href="/about" className={pathname === "/about" ? "landing-nav-active" : ""}>
          About
        </Link>
        <Link href="https://github.com/JoshMcQ/SparkPilot" target="_blank" rel="noopener noreferrer">
          Docs
        </Link>
        <ThemeToggle />
        <a href={appHref("/login")} className="landing-btn landing-btn-ghost landing-nav-cta">
          Log in
        </a>
        <Link href="/getting-started" className="landing-btn landing-btn-primary landing-nav-cta">
          Start Here
        </Link>
      </div>
    </nav>
  );
}
