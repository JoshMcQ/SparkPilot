"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/theme-toggle";

export function LandingNav() {
  const pathname = usePathname();

  return (
    <nav className="landing-nav">
      <Link href="/" className="landing-nav-brand">
        <strong>SparkPilot</strong>
      </Link>
      <div className="landing-nav-links">
        <Link href="/#features" className={pathname === "/" ? "" : ""}>
          Features
        </Link>
        <Link href="/#integrations">
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
        <Link href="/login" className="landing-btn landing-btn-ghost landing-nav-cta">
          Log in
        </Link>
        <Link href="/contact" className="landing-btn landing-btn-primary landing-nav-cta">
          Get Started
        </Link>
      </div>
    </nav>
  );
}
