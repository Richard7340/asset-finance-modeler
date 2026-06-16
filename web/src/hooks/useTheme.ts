import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

const KEY = "afm-theme";

/** Read the persisted theme, falling back to the OS preference, then light. */
function initialTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const stored = window.localStorage.getItem(KEY);
  if (stored === "light" || stored === "dark") return stored;
  const prefersDark =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  return prefersDark ? "dark" : "light";
}

/** Apply the theme to <html> (the `dark` class drives Tailwind + CSS overrides). */
function apply(theme: Theme) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
}

/**
 * Light/dark theme, persisted in localStorage. The toggle flips the `dark`
 * class on <html>; the palette is driven by `dark:` Tailwind variants plus a
 * set of CSS overrides in index.css so every existing component reads well in
 * both themes without per-utility edits.
 */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    apply(theme);
    try {
      window.localStorage.setItem(KEY, theme);
    } catch {
      // Ignore storage failures (private mode, etc.).
    }
  }, [theme]);

  const toggle = () => setTheme((t) => (t === "dark" ? "light" : "dark"));
  return { theme, toggle };
}
