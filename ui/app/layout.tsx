import type { Metadata } from "next";
import { IBM_Plex_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { TopNav } from "@/components/top-nav";
import { UserAuthPanel } from "@/components/user-auth-panel";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "SparkPilot",
  description: "Managed Spark BYOC control plane",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${plexSans.variable} ${jetbrainsMono.variable}`}>
        <main className="page">
          <header className="header">
            <div>
              <h1>SparkPilot</h1>
              <div className="subtle">AWS-first BYOC Spark runtime control plane</div>
            </div>
            <TopNav />
          </header>
          <UserAuthPanel />
          {children}
        </main>
      </body>
    </html>
  );
}
