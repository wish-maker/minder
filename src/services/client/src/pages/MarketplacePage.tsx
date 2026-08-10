import { useCallback, useEffect, useState } from "react";

import { useConfirm } from "../components/ConfirmDialog";
import { LoginPanel } from "../components/LoginPanel";
import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useDebouncedValue } from "../lib/useDebouncedValue";
import {
  badgeClass,
  cardClass,
  destructiveButtonClass,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
  statusClass,
} from "../lib/ui";

interface Plugin {
  id: string;
  name: string;
  display_name: string;
  description: string | null;
  author: string;
  repository_url: string | null;
  distribution_type: "git" | "docker" | "hybrid";
  docker_image: string | null;
  current_version: string | null;
  pricing_model: "free" | "paid" | "freemium";
  base_tier: string;
  status: "pending" | "approved" | "rejected" | "archived";
  featured: boolean;
  download_count: number;
  rating_average: number | null;
  rating_count: number;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  developer_id: string | null;
  category_id: string | null;
}

interface PluginListResponse {
  plugins: Plugin[];
  count: number;
  total: number;
  limit: number;
  offset: number;
}

interface Installation {
  installation_id: string;
  plugin_id: string;
  version: string | null;
  status: string;
  enabled: boolean;
  installed_at: string;
  last_updated_at: string;
  name: string;
  display_name: string;
  description: string | null;
  current_version: string | null;
  pricing_model: string;
  base_tier: string;
  category_id: string | null;
  author: string | null;
}

interface MyInstallationsResponse {
  installations: Installation[];
  count: number;
}

interface DependencyEntry {
  plugin_id: string;
  name: string;
  depth: number;
}

interface ConflictEntry {
  plugin_id: string;
  name: string;
  reason: string;
}

interface Recommendation {
  plugin_id: string;
  name: string;
  score: number;
}

function PricingBadge({ plugin }: { plugin: Plugin }) {
  return (
    <span className={badgeClass}>
      {plugin.pricing_model} · {plugin.base_tier}
    </span>
  );
}

function DependencyPanel({ pluginId }: { pluginId: string }) {
  const [loaded, setLoaded] = useState(false);
  const [deps, setDeps] = useState<DependencyEntry[]>([]);
  const [conflicts, setConflicts] = useState<ConflictEntry[]>([]);
  const [status, setStatus] = useState("");

  async function handleToggle(e: React.SyntheticEvent<HTMLDetailsElement>) {
    if (!e.currentTarget.open || loaded) return;
    setStatus("Loading…");
    try {
      const [depsRes, conflictsRes] = await Promise.all([
        apiFetch<{ dependencies: DependencyEntry[] }>(
          `/v1/graph/dependencies/${pluginId}`,
        ),
        apiFetch<{ conflicts: ConflictEntry[] }>(`/v1/graph/conflicts/${pluginId}`),
      ]);
      setDeps(depsRes.dependencies);
      setConflicts(conflictsRes.conflicts);
      setLoaded(true);
      setStatus("");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <details className="mt-2" onToggle={handleToggle}>
      <summary className="cursor-pointer text-xs font-medium text-indigo-600 dark:text-indigo-400">
        Dependencies &amp; conflicts
      </summary>
      <div className="mt-2 text-xs text-gray-600 dark:text-gray-400">
        {status && <p>{status}</p>}
        {loaded && deps.length === 0 && conflicts.length === 0 && (
          <p>
            No dependency or conflict data recorded for this plugin yet — the
            dependency graph is built incrementally as plugins declare
            relationships to each other.
          </p>
        )}
        {deps.length > 0 && (
          <div className="mb-1">
            <strong>Depends on:</strong>{" "}
            {deps.map((d) => d.name).join(", ")}
          </div>
        )}
        {conflicts.length > 0 && (
          <div>
            <strong>Conflicts with:</strong>{" "}
            {conflicts.map((c) => `${c.name} (${c.reason})`).join(", ")}
          </div>
        )}
      </div>
    </details>
  );
}

function PluginCard({
  plugin,
  installation,
  token,
  isAuthenticated,
  onInstalled,
  onUninstalled,
  onToggleEnabled,
  confirm,
}: {
  plugin: Plugin;
  installation: Installation | undefined;
  token: string;
  isAuthenticated: boolean;
  onInstalled: () => void;
  onUninstalled: (pluginId: string) => void;
  onToggleEnabled: (pluginId: string, enabled: boolean) => void;
  confirm: ReturnType<typeof useConfirm>["confirm"];
}) {
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleInstall() {
    setBusy(true);
    setStatus("Installing…");
    try {
      await apiFetch(`/v1/marketplace/plugins/${plugin.id}/install`, {
        method: "POST",
        token,
      });
      onInstalled();
      setStatus("");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  async function handleUninstall() {
    const ok = await confirm({
      title: "Uninstall plugin?",
      message: `This removes "${plugin.display_name}" and disables anything it was doing (data already collected is kept).`,
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    setStatus("Uninstalling…");
    try {
      await apiFetch(`/v1/marketplace/plugins/${plugin.id}/uninstall`, {
        method: "DELETE",
        token,
      });
      onUninstalled(plugin.id);
      setStatus("");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  async function handleToggleEnabled() {
    if (!installation) return;
    const nextEnabled = !installation.enabled;
    setBusy(true);
    setStatus(nextEnabled ? "Enabling…" : "Disabling…");
    try {
      await apiFetch(
        `/v1/marketplace/plugins/${plugin.id}/${nextEnabled ? "enable" : "disable"}`,
        { method: "POST", token },
      );
      onToggleEnabled(plugin.id, nextEnabled);
      setStatus("");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  return (
    <section className={`mb-4 ${cardClass}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-gray-900 dark:text-gray-100">
            <span aria-hidden="true">🧩</span> {plugin.display_name}
            {plugin.featured && <span className={badgeClass}>⭐ featured</span>}
          </h2>
          {plugin.description && (
            <p className="mt-0.5 text-sm text-gray-600 dark:text-gray-400">
              {plugin.description}
            </p>
          )}
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            by {plugin.author}
            {plugin.rating_count > 0 &&
              plugin.rating_average != null &&
              ` · ${plugin.rating_average.toFixed(1)}★ (${plugin.rating_count})`}
            {" · "}
            {plugin.download_count} install{plugin.download_count === 1 ? "" : "s"}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <PricingBadge plugin={plugin} />
            {plugin.category_id && (
              <span className={badgeClass}>{plugin.category_id}</span>
            )}
          </div>
          <DependencyPanel pluginId={plugin.id} />
        </div>
        <div className="flex flex-shrink-0 flex-col items-end gap-1.5">
          {!installation ? (
            <button
              onClick={handleInstall}
              disabled={!isAuthenticated || busy}
              className={primaryButtonClass}
            >
              Install
            </button>
          ) : (
            <>
              <button
                onClick={handleToggleEnabled}
                disabled={busy}
                className={secondaryButtonClass}
              >
                {installation.enabled ? "Disable" : "Enable"}
              </button>
              <button
                onClick={handleUninstall}
                disabled={busy}
                className={destructiveButtonClass}
              >
                🗑 Uninstall
              </button>
              <span className={badgeClass}>
                {installation.enabled ? "✓ enabled" : "disabled"}
              </span>
            </>
          )}
          {!isAuthenticated && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Log in to install
            </span>
          )}
        </div>
      </div>
      {status && <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{status}</p>}
    </section>
  );
}

function SearchAndFilters({
  query,
  onQueryChange,
}: {
  query: string;
  onQueryChange: (q: string) => void;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-3">
      <input
        className={`${inputClass} max-w-xs`}
        type="text"
        placeholder="Search plugins…"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
      />
    </div>
  );
}

function InstalledPluginRow({
  installation,
  token,
  onUninstalled,
  onToggleEnabled,
  confirm,
}: {
  installation: Installation;
  token: string;
  onUninstalled: (pluginId: string) => void;
  onToggleEnabled: (pluginId: string, enabled: boolean) => void;
  confirm: ReturnType<typeof useConfirm>["confirm"];
}) {
  const [status, setStatus] = useState("");

  async function handleUninstall() {
    const ok = await confirm({
      title: "Uninstall plugin?",
      message: `This removes "${installation.display_name}" and disables anything it was doing (data already collected is kept).`,
      danger: true,
    });
    if (!ok) return;
    setStatus("Uninstalling…");
    try {
      await apiFetch(`/v1/marketplace/plugins/${installation.plugin_id}/uninstall`, {
        method: "DELETE",
        token,
      });
      onUninstalled(installation.plugin_id);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleToggle() {
    const nextEnabled = !installation.enabled;
    setStatus(nextEnabled ? "Enabling…" : "Disabling…");
    try {
      await apiFetch(
        `/v1/marketplace/plugins/${installation.plugin_id}/${nextEnabled ? "enable" : "disable"}`,
        { method: "POST", token },
      );
      onToggleEnabled(installation.plugin_id, nextEnabled);
      setStatus("");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <li className="flex items-center justify-between gap-3 rounded-md bg-gray-50 px-3 py-2 text-sm dark:bg-gray-800">
      <span>
        🧩 {installation.display_name}{" "}
        <span className={badgeClass}>
          {installation.enabled ? "✓ enabled" : "disabled"}
        </span>
      </span>
      <span className="flex items-center gap-2">
        <span className="text-xs text-gray-500 dark:text-gray-400">{status}</span>
        <button onClick={handleToggle} className={secondaryButtonClass}>
          {installation.enabled ? "Disable" : "Enable"}
        </button>
        <button onClick={handleUninstall} className={destructiveButtonClass}>
          🗑 Uninstall
        </button>
      </span>
    </li>
  );
}

export function MarketplacePage() {
  const { token, isAuthenticated } = useAuth();
  const { confirm, dialog } = useConfirm();
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [queryInput, setQueryInput] = useState("");
  const query = useDebouncedValue(queryInput, 300);
  const [myInstallations, setMyInstallations] = useState<Installation[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  const loadPlugins = useCallback(
    async (nextOffset: number, replace: boolean) => {
      setStatusMsg("Loading…");
      try {
        const path = query.trim()
          ? `/v1/marketplace/plugins/search?q=${encodeURIComponent(query.trim())}&limit=20&offset=${nextOffset}`
          : `/v1/marketplace/plugins?limit=20&offset=${nextOffset}`;
        const res = await apiFetch<PluginListResponse>(path);
        setPlugins((prev) => (replace ? res.plugins : [...prev, ...res.plugins]));
        setTotal(res.total);
        setOffset(nextOffset);
        setStatusMsg("");
      } catch (e) {
        setStatusMsg(e instanceof Error ? e.message : String(e), true);
      }
    },
    [query, setStatusMsg],
  );

  const loadMyInstallations = useCallback(async () => {
    if (!isAuthenticated) {
      setMyInstallations([]);
      return;
    }
    try {
      const res = await apiFetch<MyInstallationsResponse>(
        "/v1/marketplace/installations/me",
        { token },
      );
      setMyInstallations(res.installations);
      if (res.installations.length > 0) {
        const ids = res.installations.map((i) => i.plugin_id);
        try {
          const rec = await apiFetch<{ recommendations: Recommendation[] }>(
            "/v1/graph/recommendations?limit=5",
            { method: "POST", body: ids, token },
          );
          setRecommendations(rec.recommendations);
        } catch {
          // recommendations are a nice-to-have; ignore failures quietly
        }
      } else {
        setRecommendations([]);
      }
    } catch {
      // best-effort -- an install action will surface its own error
    }
  }, [isAuthenticated, token]);

  useEffect(() => {
    loadPlugins(0, true);
    // query changes trigger a fresh search from offset 0 (see loadPlugins' own deps)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  useEffect(() => {
    loadMyInstallations();
  }, [loadMyInstallations]);

  function installationFor(pluginId: string) {
    return myInstallations.find((i) => i.plugin_id === pluginId);
  }

  function handleUninstalled(pluginId: string) {
    setMyInstallations((prev) => prev.filter((i) => i.plugin_id !== pluginId));
  }

  function handleToggleEnabled(pluginId: string, enabled: boolean) {
    setMyInstallations((prev) =>
      prev.map((i) => (i.plugin_id === pluginId ? { ...i, enabled } : i)),
    );
  }

  return (
    <>
      {dialog}
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Browse and install Minder plugins. Browsing is open for everyone; log
        in to install, enable, disable, or uninstall.
      </p>
      <LoginPanel onStatus={setStatusMsg} />
      <div className={statusClass(isError)}>{status}</div>

      {isAuthenticated && myInstallations.length > 0 && (
        <section className={`mb-6 ${cardClass}`}>
          <h2 className="mb-2 text-base font-semibold text-gray-900 dark:text-gray-100">
            <span aria-hidden="true">✅</span> My Installed Plugins
          </h2>
          <ul className="flex flex-col gap-1.5">
            {myInstallations.map((i) => (
              <InstalledPluginRow
                key={i.plugin_id}
                installation={i}
                token={token}
                onUninstalled={handleUninstalled}
                onToggleEnabled={handleToggleEnabled}
                confirm={confirm}
              />
            ))}
          </ul>
          {recommendations.length > 0 && (
            <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
              Recommended based on what you've installed:{" "}
              {recommendations.map((r) => r.name).join(", ")}
            </p>
          )}
        </section>
      )}

      <SearchAndFilters query={queryInput} onQueryChange={setQueryInput} />

      {plugins.length === 0 && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {query
            ? "No plugins match your search."
            : "No plugins in the catalog yet."}
        </p>
      )}
      {plugins.map((plugin) => (
        <PluginCard
          key={plugin.id}
          plugin={plugin}
          installation={installationFor(plugin.id)}
          token={token}
          isAuthenticated={isAuthenticated}
          onInstalled={loadMyInstallations}
          onUninstalled={handleUninstalled}
          onToggleEnabled={handleToggleEnabled}
          confirm={confirm}
        />
      ))}
      {plugins.length < total && (
        <button
          onClick={() => loadPlugins(offset + 20, false)}
          className={secondaryButtonClass}
        >
          Load more
        </button>
      )}
    </>
  );
}
