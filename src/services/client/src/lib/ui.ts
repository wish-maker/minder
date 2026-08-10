/**
 * Shared Tailwind class constants — previously copy-pasted byte-for-byte into
 * every page that needed them (6 identical strings, 4-7 files each). Centralized
 * here so a style change (or an accessibility fix, like the focus-visible rings
 * added below) lands once instead of N times.
 */

export const inputClass =
  "w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm outline-none focus:border-indigo-400 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-600 dark:bg-gray-800";

/** Compact, non-full-width variant for inline rows (e.g. the login form). */
export const inlineInputClass =
  "rounded-md border border-gray-300 px-3 py-1.5 text-sm outline-none focus:border-indigo-400 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-600 dark:bg-gray-800";

export const primaryButtonClass =
  "rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50 outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1";

export const secondaryButtonClass =
  "rounded-md border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:hover:bg-gray-800 outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1";

/** Filled, high-emphasis red button for destructive, hard-to-undo actions
 * (delete KB, uninstall plugin, delete model) -- every use site on this app
 * turned out to be genuinely destructive, so there's no separate low-emphasis
 * "danger" variant; a routine toggle (disable, not delete) uses
 * secondaryButtonClass instead. */
export const destructiveButtonClass =
  "rounded-md bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50 outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-1";

/** Base card surface -- margin/layout classes (mb-4, flex, gap-*, hover
 * variants) are call-site concerns and stay inline; only the surface itself
 * (border/bg/radius/shadow) was actually identical across every use site. */
export const cardClass =
  "rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-900";

export const badgeClass =
  "inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-300";

export const statusClass = (isError: boolean) =>
  `mb-4 min-h-5 text-sm ${isError ? "text-red-600" : "text-gray-500 dark:text-gray-400"}`;
