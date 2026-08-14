/** Animated placeholder block for a value that's still loading -- replaces a
 * bare "Loading…" line on pages where the eventual content has a known shape
 * (a stat number, a health strip) so the layout doesn't jump once data
 * arrives. `inline` renders a `<span>` instead of a `<div>` -- required
 * wherever this stands in for text inside a `<p>`/`<h2>`/etc., since a `<div>`
 * there is invalid HTML nesting (React's validateDOMNesting warning). */
export function Skeleton({
  className = "",
  inline = false,
}: {
  className?: string;
  inline?: boolean;
}) {
  const Tag = inline ? "span" : "div";
  return (
    <Tag
      aria-hidden="true"
      className={`inline-block animate-pulse rounded-md bg-gray-200 dark:bg-gray-800 ${className}`}
    />
  );
}
