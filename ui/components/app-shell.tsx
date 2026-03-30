"use client";

import { usePathname } from "next/navigation";
import { TopNav } from "@/components/top-nav";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserAuthPanel } from "@/components/user-auth-panel";

/**
 * Wraps the internal app chrome (header, nav, auth panel).
 * Hidden on the landing page (/) so it renders as a clean marketing page.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const MARKETING_ROUTES = ["/", "/pricing", "/login", "/getting-started", "/about", "/contact", "/security"];
  const isLanding = MARKETING_ROUTES.includes(pathname);

  if (isLanding) {
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
