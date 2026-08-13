import type { ReactNode } from "react";

import { mutedTextClass } from "../lib/ui";

/** The "nothing here yet" line every list page rendered as its own
 * `<p className="text-sm text-gray-500 dark:text-gray-400">…</p>` (KB, models,
 * plugins, tools, …). Centralized so the empty-list voice stays consistent and
 * a later visual upgrade (icon, centered card) lands once (#509).
 *
 * Children carry the message so callers can still embed a link ("browse
 * Available Plugins") or vary the copy for the search-vs-truly-empty case. */
export function EmptyState({ children }: { children: ReactNode }) {
  return <p className={mutedTextClass}>{children}</p>;
}
