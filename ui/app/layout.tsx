import type { Metadata } from "next";
import { IBM_Plex_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import "./marketing-pages.css";
import { AppShell } from "@/components/app-shell";

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
          <AppShell>
            {children}
          </AppShell>
        </main>
      </body>
    </html>
  );
}
