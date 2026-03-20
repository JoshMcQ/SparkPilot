"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "sparkpilot.theme";

type ThemeMode = "light" | "dark";

function applyTheme(theme: ThemeMode): void {
  document.documentElement.dataset.theme = theme;
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<ThemeMode>("light");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const next = window.localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
    applyTheme(next);
    const timer = window.setTimeout(() => {
      setTheme(next);
      setReady(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!ready) {
      return;
    }
    applyTheme(theme);
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [ready, theme]);

  function toggleTheme() {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  }

  const nextTheme = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggleTheme}
      aria-label={ready ? `Switch to ${nextTheme} mode` : "Toggle theme"}
      aria-pressed={ready ? theme === "dark" : undefined}
      title={ready ? `Switch to ${nextTheme} mode` : "Toggle theme"}
      suppressHydrationWarning
    >
      {ready && theme === "dark" ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      ) : ready ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
      ) : null}
    </button>
  );
}
