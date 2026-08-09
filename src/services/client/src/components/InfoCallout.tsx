import type { ReactNode } from "react";

/** A small tinted callout box for a clarifying note -- distinct from a plain
 * paragraph so it reads as "important context," not body copy. */
export function InfoCallout({
  icon = "ℹ️",
  children,
}: {
  icon?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex gap-2 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-100">
      <span aria-hidden="true">{icon}</span>
      <div>{children}</div>
    </div>
  );
}
