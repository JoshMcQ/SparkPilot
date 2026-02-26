import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "SparkPilot",
  description: "Managed Spark BYOC control plane"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <main className="page">
          <header className="header">
            <div>
              <h1>SparkPilot</h1>
              <div className="subtle">AWS-first BYOC Spark runtime control plane</div>
            </div>
            <nav className="nav">
              <Link href="/">Overview</Link>
              <Link href="/environments">Environments</Link>
              <Link href="/runs">Runs</Link>
            </nav>
          </header>
          {children}
        </main>
      </body>
    </html>
  );
}

