import type { ReactNode } from "react";

import { mutedTextClass } from "../lib/ui";

/** The "nothing here yet" line every list page rendered as its own
 * `<p className="text-sm text-gray-500 dark:text-gray-400">…</p>` (KB, models,
 * plugins, tools, …). Centralized so the empty-list voice stays consistent and
 * a later visual upgrade (icon, centered card) lands once (#509).
 *
 * Children carry the message so callers can still embed a link ("browse
 * Available Plugins") or vary the copy for the search-vs-truly-empty case.
 * `className` appends layout-only tweaks (e.g. a `mb-6` between two list
 * sections) without re-spelling the muted-text token. */
export function EmptyState({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <p className={className ? `${mutedTextClass} ${className}` : mutedTextClass}>
      {children}
    </p>
  );
}
