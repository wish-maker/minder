/** Case-insensitive "type to narrow a list" filter, shared by the management
 * pages so the behaviour is identical everywhere (KnowledgeBases, RagPipelines,
 * ModelManagement each hand-rolled the same `needle = query.trim().toLowerCase()`
 * + `.some(f => f.includes(needle))` dance).
 *
 * `fields` maps an item to the strings a match should consider. A blank query
 * returns the list unchanged (no filtering).
 */
export function filterByText<T>(
  items: readonly T[],
  query: string,
  fields: (item: T) => string[],
): T[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [...items];
  return items.filter((item) =>
    fields(item).some((f) => f.toLowerCase().includes(needle)),
  );
}
