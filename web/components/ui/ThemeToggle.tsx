"use client";
import { useEffect, useState } from "react";
import { Moon, Sun } from "./Icons";

type Theme = "light" | "dark";

/** Reads the theme the inline script in layout.tsx already applied, and switches it. Storage is optional. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null);
  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  }, []);
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => {
        document.documentElement.dataset.theme = next;
        setTheme(next);
        try {
          localStorage.setItem("repopilot.theme", next);
        } catch {
          /* private mode: the choice just lasts for this visit */
        }
      }}
      className="press inline-flex h-11 w-11 items-center justify-center rounded-md text-ink hover:bg-surface-2"
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
    >
      <span key={theme} className="pop inline-flex">
        {theme === "dark" ? <Sun /> : <Moon />}
      </span>
    </button>
  );
}
