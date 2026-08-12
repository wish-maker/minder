import type { ReactNode } from "react";

import { statusClass } from "../lib/ui";

/** Accessible status/error line shared across pages.
 *
 * Previously every page rendered a bare `<div className={statusClass(isError)}>`,
 * which signals errors by COLOUR ONLY and is invisible to assistive tech. This
 * wraps that with a live region so screen readers announce status changes
 * ("Loading…", errors) — polite for info, assertive for errors — and carries the
 * same visual class so it's a drop-in replacement. Empty content renders nothing.
 *
 * App-wide adoption is tracked in the client-modernization epic (#509); this is the
 * reusable primitive it standardises on. */
export function StatusLine({
  isError = false,
  children,
  className,
}: {
  isError?: boolean;
  children: ReactNode;
  className?: string;
}) {
  const base = statusClass(isError);
  return (
    <div
      className={className ? `${base} ${className}` : base}
      role={isError ? "alert" : "status"}
      aria-live={isError ? "assertive" : "polite"}
    >
      {children}
    </div>
  );
}
