import { useCallback, useEffect } from "react";

import { EmptyState } from "../components/EmptyState";
import { InfoCallout } from "../components/InfoCallout";
import { PageHeader } from "../components/PageHeader";
import { StatusLine } from "../components/StatusLine";
import { apiFetch } from "../lib/api";
import { badgeClass, secondaryButtonClass } from "../lib/ui";
import { useAsyncResource } from "../lib/useAsyncResource";
import { usePaginatedList } from "../lib/usePaginatedList";

interface LiveTool {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  };
  metadata: {
    plugin: string;
    endpoint: string;
    method: string;
  };
}

interface LiveToolsResponse {
  tools: LiveTool[];
}

interface CatalogTool {
  id: string;
  plugin_id: string;
  plugin_name: string;
  plugin_display_name: string;
  tool_name: string;
  type: string;
  description: string | null;
  endpoint: string;
  method: string;
  required_tier: string;
  active: boolean;
}

interface CatalogToolsResponse {
  tools: CatalogTool[];
  count: number;
  total: number;
  limit: number;
  offset: number;
}

function LiveToolCard({ tool }: { tool: LiveTool }) {
  return (
    <section className="mb-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">⚡</span> {tool.function.name}
        <span className={badgeClass}>{tool.metadata.plugin}</span>
      </h3>
      <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
        {tool.function.description || "No description provided."}
      </p>
      <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
        {tool.metadata.method} {tool.metadata.endpoint}
      </p>
    </section>
  );
}

function CatalogToolCard({ tool }: { tool: CatalogTool }) {
  return (
    <section className="mb-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">🧰</span> {tool.tool_name}
        <span className={badgeClass}>{tool.plugin_display_name}</span>
        <span className={badgeClass}>{tool.required_tier}</span>
        {!tool.active && (
          <span className="inline-block rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">
            inactive
          </span>
        )}
      </h3>
      <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
        {tool.description || "No description provided."}
      </p>
      <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
        {tool.method} {tool.endpoint}
      </p>
    </section>
  );
}

export function AiToolsPage() {
  // Live tools are a single whole-object read — the canonical useAsyncResource
  // case (cancels on unmount, guards against a stale response). #502
  const liveTools = useAsyncResource(
    (signal) =>
      apiFetch<LiveToolsResponse>("/v1/plugins/ai/tools", { signal }).then(
        (r) => r.tools,
      ),
    { timeoutMs: 15_000 },
  );

  const fetchCatalogPage = useCallback(async (offset: number) => {
    const res = await apiFetch<CatalogToolsResponse>(
      `/v1/marketplace/ai/tools?active_only=false&limit=20&offset=${offset}`,
    );
    return { items: res.tools, total: res.total };
  }, []);
  const {
    items: catalogTools,
    status: catalogStatus,
    reload: reloadCatalogTools,
    loadMore: loadMoreCatalogTools,
    hasMore: hasMoreCatalogTools,
  } = usePaginatedList(fetchCatalogPage);

  useEffect(() => {
    // usePaginatedList doesn't self-load; liveTools (useAsyncResource) does.
    reloadCatalogTools();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <PageHeader icon="🧰" title="AI Tools" />
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Every function-calling tool Minder's plugins expose, from two angles.
        This page has nothing to log in for — it's read-only either way.
      </p>

      <h2 className="mb-1 text-base font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">⚡</span> Live Tools
      </h2>
      <InfoCallout icon="ℹ️">
        Computed fresh on every request from the plugins actually running
        right now on Plugin Registry. This is exactly what the AI chat's
        function-calling feeds on — if a plugin isn't running, its tools
        won't appear here even if they're in the catalog below.
      </InfoCallout>
      <StatusLine isError={!!liveTools.error}>
        {liveTools.error ?? (liveTools.loading ? "Loading…" : "")}
      </StatusLine>
      {liveTools.data !== null && liveTools.data.length === 0 && (
        <EmptyState className="mb-6">
          No plugin is currently exposing an AI tool.
        </EmptyState>
      )}
      <div className="mb-6">
        {liveTools.data?.map((t) => (
          <LiveToolCard key={`${t.metadata.plugin}:${t.function.name}`} tool={t} />
        ))}
      </div>

      <h2 className="mb-1 text-base font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">🧰</span> Catalog
      </h2>
      <InfoCallout icon="ℹ️">
        The durable tool catalog Marketplace keeps, with tier info — includes
        tools from plugins that aren't running right now, and can lag behind
        Live Tools above since it's only updated when a plugin (re)loads.
      </InfoCallout>
      <StatusLine isError={false}>{catalogStatus}</StatusLine>
      {catalogTools.length === 0 && (
        <EmptyState>No AI tools in the catalog yet.</EmptyState>
      )}
      {catalogTools.map((t) => (
        <CatalogToolCard key={t.id} tool={t} />
      ))}
      {hasMoreCatalogTools && (
        <button onClick={loadMoreCatalogTools} className={secondaryButtonClass}>
          Load more
        </button>
      )}
    </>
  );
}
