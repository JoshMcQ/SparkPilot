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
      className="button button-sm button-secondary theme-toggle"
      onClick={toggleTheme}
      aria-label={ready ? `Switch to ${nextTheme} mode` : "Toggle theme"}
      aria-pressed={ready ? theme === "dark" : undefined}
      suppressHydrationWarning
    >
      <span suppressHydrationWarning>{ready ? (theme === "dark" ? "☀️ Light" : "🌙 Dark") : "Theme"}</span>
    </button>
  );
}
