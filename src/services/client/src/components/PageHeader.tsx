/** Every leaf page's own title (#<issue>) -- replaced SectionTabs' shared
 * section-level heading (e.g. every RAG sub-page showed the same bare "RAG"
 * title) now that the sidebar, not a horizontal tab strip, carries section
 * navigation. A specific title per page ("RAG Pipelines", not "RAG") is
 * the point: landing on a deep link should tell you exactly what page
 * you're on without needing to check which sidebar item is highlighted. */
export function PageHeader({
  icon,
  title,
}: {
  icon: string;
  title: string;
}) {
  return (
    <h1 className="mb-2 text-2xl font-bold text-gray-900 dark:text-gray-100">
      <span aria-hidden="true">{icon}</span> {title}
    </h1>
  );
}
