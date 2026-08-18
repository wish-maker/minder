import { useState } from "react";

import { getTheme, setTheme, type Theme } from "../lib/theme";

const ORDER: Theme[] = ["system", "light", "dark"];
const ICON: Record<Theme, string> = { system: "🖥️", light: "☀️", dark: "🌙" };
const LABEL: Record<Theme, string> = { system: "System", light: "Light", dark: "Dark" };

/** One button, cycling system -> light -> dark -> system. A 3-way toggle
 * (rather than a plain light/dark switch) keeps "follow my OS" available as
 * an explicit, nameable state instead of just "whatever it happened to boot
 * into." */
export function ThemeToggle() {
  const [theme, setThemeState] = useState<Theme>(() => getTheme());

  function cycle() {
    const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
    setTheme(next);
    setThemeState(next);
  }

  return (
    <button
      type="button"
      onClick={cycle}
      title={`Theme: ${LABEL[theme]} (click to change)`}
      aria-label={`Theme: ${LABEL[theme]}. Click to switch.`}
      className="rounded-md p-1.5 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
    >
      <span aria-hidden="true">{ICON[theme]}</span>
    </button>
  );
}
