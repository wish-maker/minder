/** Animated placeholder block for a value that's still loading -- replaces a
 * bare "Loading…" line on pages where the eventual content has a known shape
 * (a stat number, a health strip) so the layout doesn't jump once data
 * arrives. */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-md bg-gray-200 dark:bg-gray-800 ${className}`}
    />
  );
}
