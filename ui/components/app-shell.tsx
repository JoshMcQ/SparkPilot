"use client";

import { usePathname } from "next/navigation";
import { TopNav } from "@/components/top-nav";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserAuthPanel } from "@/components/user-auth-panel";

/**
 * Wraps the internal app chrome (header, nav, auth panel).
 * Hidden on auth-only routes where chrome is not needed.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const CHROMELESS_ROUTES = ["/login", "/auth/callback"];
  const isChromeless = CHROMELESS_ROUTES.includes(pathname);

  if (isChromeless) {
    return <>{children}</>;
  }

  return (
    <>
      <header className="header">
        <div>
          <h1>SparkPilot</h1>
          <div className="subtle">AWS-first BYOC Spark runtime control plane</div>
          <div className="subtle">Authenticated product area</div>
        </div>
        <div className="header-actions">
          <TopNav />
          <ThemeToggle />
        </div>
      </header>
      <UserAuthPanel />
      {children}
    </>
  );
}
