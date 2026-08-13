import { useCallback, useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";

import { useConfirm } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { StatusLine } from "../components/StatusLine";
import { apiFetch, friendlyErrorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  badgeClass,
  cardClass,
  destructiveButtonClass,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "../lib/ui";

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
  requires_services: string[];
}

interface MyInstallationsResponse {
  installations: Installation[];
  count: number;
}

interface ConfigField {
  key: string;
  type?: "string" | "int" | "float" | "bool";
  secret?: boolean;
  description?: string;
}

interface PluginConfigResponse {
  configurable: boolean;
  schema: ConfigField[];
  values: Record<string, unknown>;
}

function fieldToInputType(field: ConfigField): "checkbox" | "password" | "number" | "text" {
  if (field.type === "bool") return "checkbox";
  if (field.secret) return "password";
  if (field.type === "int" || field.type === "float") return "number";
  return "text";
}

function FieldInput({
  id,
  field,
  value,
  onChange,
}: {
  id: string;
  field: ConfigField;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const inputType = fieldToInputType(field);

  if (inputType === "checkbox") {
    return (
      <input
        id={id}
        className="h-4 w-4 rounded border-gray-300"
        type="checkbox"
        checked={!!value}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }
  if (inputType === "password") {
    return (
      <input
        id={id}
        className={inputClass}
        type="password"
        placeholder="unchanged (leave blank to keep current value)"
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  if (inputType === "number") {
    return (
      <input
        id={id}
        className={inputClass}
        type="number"
        step={field.type === "float" ? "any" : undefined}
        defaultValue={value as number | string}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <input
      id={id}
      className={inputClass}
      type="text"
      defaultValue={value as string}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

/** Lazily fetches this plugin's config schema on first expand -- merged in
 * from the old standalone "Plugin Configuration" page, which made a user
 * pick the same plugin twice (once to install it here, once to find it
 * again in a completely separate page to configure it). "configurable"
 * here isn't guaranteed by "installed": plugin-registry's config schema
 * and marketplace's installation record are two independent systems linked
 * only by a name match, so a plugin can be installed with no schema, or
 * (for first-party plugins that just run regardless of any per-user
 * install) have a schema without ever appearing as "installed" for a given
 * user -- this panel only ever claims the former case, honestly. */
function ConfigurePanel({ name, token }: { name: string; token: string }) {
  const baseId = useId();
  const [loaded, setLoaded] = useState(false);
  const [configurable, setConfigurable] = useState(false);
  const [schema, setSchema] = useState<ConfigField[]>([]);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [status, setStatus] = useState("");

  async function handleToggle(e: React.SyntheticEvent<HTMLDetailsElement>) {
    if (!e.currentTarget.open || loaded) return;
    setStatus("Loading…");
    try {
      const cfg = await apiFetch<PluginConfigResponse>(
        `/v1/plugins/${encodeURIComponent(name)}/config`,
        { token },
      );
      setConfigurable(cfg.configurable);
      setSchema(cfg.schema);
      setValues(cfg.values);
      setLoaded(true);
      setStatus("");
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const body: Record<string, unknown> = {};
    const skipped: string[] = [];
    for (const field of schema) {
      if (!(field.key in draft)) continue;
      const raw = draft[field.key];
      if (field.secret && raw === "") continue; // unchanged
      if (field.type === "int" || field.type === "float") {
        const parsed = field.type === "int" ? parseInt(String(raw), 10) : parseFloat(String(raw));
        // An emptied/invalid number field used to serialize as `null` here
        // (JSON.stringify(NaN) === "null") and save silently -- clearing a
        // field by accident wiped the stored value with no warning. Treat
        // it as "no change" instead, same as an untouched secret field.
        if (Number.isNaN(parsed)) {
          skipped.push(field.key);
          continue;
        }
        body[field.key] = parsed;
      } else {
        body[field.key] = raw;
      }
    }
    setStatus("Saving…");
    try {
      await apiFetch(`/v1/plugins/${encodeURIComponent(name)}/config`, {
        method: "PUT",
        body,
        token,
      });
      setStatus(
        skipped.length > 0
          ? `Saved (left ${skipped.join(", ")} unchanged — not a valid number).`
          : "Saved.",
      );
      setTimeout(() => setStatus(""), skipped.length > 0 ? 4000 : 2000);
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
  }

  return (
    <details className="mt-3 border-t border-gray-100 pt-3 dark:border-gray-800" onToggle={handleToggle}>
      <summary className="cursor-pointer text-sm font-medium text-indigo-600 dark:text-indigo-400">
        <span aria-hidden="true">⚙</span> Configure
      </summary>
      <div className="mt-3">
        {status && <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">{status}</p>}
        {loaded && !configurable && (
          <p className="text-xs text-gray-500 dark:text-gray-400">
            This plugin has no configurable settings.
          </p>
        )}
        {loaded && configurable && (
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            {schema.map((field) => (
              <div key={field.key}>
                <label
                  htmlFor={`${baseId}-${field.key}`}
                  className="mb-1 block text-sm font-medium capitalize text-gray-700 dark:text-gray-300"
                >
                  {field.key}
                </label>
                <FieldInput
                  id={`${baseId}-${field.key}`}
                  field={field}
                  value={values[field.key]}
                  onChange={(v) => setDraft((d) => ({ ...d, [field.key]: v }))}
                />
                {field.description && (
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {field.description}
                  </p>
                )}
              </div>
            ))}
            <div>
              <button type="submit" className={primaryButtonClass}>
                Save
              </button>
            </div>
          </form>
        )}
      </div>
    </details>
  );
}

function InstalledPluginCard({
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
  const [busy, setBusy] = useState(false);

  async function handleUninstall() {
    const ok = await confirm({
      title: "Uninstall plugin?",
      message: `This removes "${installation.display_name}" and disables anything it was doing (data already collected is kept).`,
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    setStatus("Uninstalling…");
    try {
      await apiFetch(`/v1/marketplace/plugins/${installation.plugin_id}/uninstall`, {
        method: "DELETE",
        token,
      });
      onUninstalled(installation.plugin_id);
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
    setBusy(false);
  }

  async function handleToggle() {
    const nextEnabled = !installation.enabled;
    setBusy(true);
    setStatus(nextEnabled ? "Enabling…" : "Disabling…");
    try {
      await apiFetch(
        `/v1/marketplace/plugins/${installation.plugin_id}/${nextEnabled ? "enable" : "disable"}`,
        { method: "POST", token },
      );
      onToggleEnabled(installation.plugin_id, nextEnabled);
      setStatus("");
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
    setBusy(false);
  }

  return (
    <section className={`mb-4 ${cardClass}`}>
      <div className="flex items-start justify-between gap-3">
        <h2 className="flex items-center gap-2 text-base font-semibold text-gray-900 dark:text-gray-100">
          <span aria-hidden="true">🧩</span> {installation.display_name}
          <span className={badgeClass}>
            {installation.enabled ? "✓ enabled" : "disabled"}
          </span>
        </h2>
        <div className="flex flex-shrink-0 items-center gap-2">
          <button onClick={handleToggle} disabled={busy} className={secondaryButtonClass}>
            {installation.enabled ? "Disable" : "Enable"}
          </button>
          <button onClick={handleUninstall} disabled={busy} className={destructiveButtonClass}>
            🗑 Uninstall
          </button>
        </div>
      </div>
      {installation.requires_services.length > 0 && (
        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
          Needs: {installation.requires_services.join(", ")}
        </p>
      )}
      {status && <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{status}</p>}
      <ConfigurePanel name={installation.name} token={token} />
    </section>
  );
}

export function InstalledPluginsPage() {
  const { token, isAuthenticated } = useAuth();
  const { confirm, dialog } = useConfirm();
  const [installations, setInstallations] = useState<Installation[] | null>(null);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  const loadInstallations = useCallback(async () => {
    if (!isAuthenticated) return;
    setStatusMsg("Loading…");
    try {
      const res = await apiFetch<MyInstallationsResponse>(
        "/v1/marketplace/installations/me",
        { token },
      );
      setInstallations(res.installations);
      setStatusMsg("");
    } catch (e) {
      setStatusMsg(friendlyErrorMessage(e), true);
    }
  }, [isAuthenticated, token, setStatusMsg]);

  useEffect(() => {
    loadInstallations();
  }, [loadInstallations]);

  function handleUninstalled(pluginId: string) {
    setInstallations((prev) => (prev ?? []).filter((i) => i.plugin_id !== pluginId));
  }

  function handleToggleEnabled(pluginId: string, enabled: boolean) {
    setInstallations((prev) =>
      (prev ?? []).map((i) => (i.plugin_id === pluginId ? { ...i, enabled } : i)),
    );
  }

  return (
    <>
      {dialog}
      <PageHeader icon="🧩" title="Installed Plugins" />
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Manage the plugins you've installed — enable, disable, uninstall, or
        edit their settings. Requires login: installs are per-user.
      </p>
      <StatusLine isError={isError}>{status}</StatusLine>
      {!isAuthenticated && (
        <EmptyState>
          Log in (top right) to see your installed plugins.
        </EmptyState>
      )}
      {isAuthenticated && installations !== null && installations.length === 0 && (
        <EmptyState>
          No plugins installed yet —{" "}
          <Link to="/marketplace/plugins/available" className="underline hover:text-indigo-600 dark:hover:text-indigo-400">
            browse Available Plugins
          </Link>
          .
        </EmptyState>
      )}
      {isAuthenticated && installations !== null && installations.length > 0 && (
        <p className="mb-4 text-xs text-gray-500 dark:text-gray-400">
          Some of these expose AI tools the assistant can call —{" "}
          <Link to="/marketplace/plugins/ai-tools" className="underline hover:text-indigo-600 dark:hover:text-indigo-400">
            check AI Tools
          </Link>{" "}
          to see which are live right now.
        </p>
      )}
      {installations?.map((i) => (
        <InstalledPluginCard
          key={i.plugin_id}
          installation={i}
          token={token}
          onUninstalled={handleUninstalled}
          onToggleEnabled={handleToggleEnabled}
          confirm={confirm}
        />
      ))}
    </>
  );
}
