import { useCallback, useEffect, useState } from "react";

import { LoginPanel } from "../components/LoginPanel";
import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";

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

interface PluginListResponse {
  plugins: { name: string }[];
}

interface PluginEntry {
  name: string;
  schema: ConfigField[];
  values: Record<string, unknown>;
}

function fieldToInputType(field: ConfigField): "checkbox" | "password" | "number" | "text" {
  if (field.type === "bool") return "checkbox";
  if (field.secret) return "password";
  if (field.type === "int" || field.type === "float") return "number";
  return "text";
}

const inputClass =
  "w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-400 focus:outline-none dark:border-gray-600 dark:bg-gray-800";

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: ConfigField;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const inputType = fieldToInputType(field);

  if (inputType === "checkbox") {
    return (
      <input
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
      className={inputClass}
      type="text"
      defaultValue={value as string}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function PluginCard({
  plugin,
  token,
}: {
  plugin: PluginEntry;
  token: string;
}) {
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [saveStatus, setSaveStatus] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const body: Record<string, unknown> = {};
    for (const field of plugin.schema) {
      if (!(field.key in draft)) continue;
      const raw = draft[field.key];
      if (field.secret && raw === "") continue; // unchanged
      if (field.type === "int") body[field.key] = parseInt(String(raw), 10);
      else if (field.type === "float") body[field.key] = parseFloat(String(raw));
      else body[field.key] = raw;
    }
    setSaveStatus("Saving…");
    try {
      await apiFetch(`/v1/plugins/${encodeURIComponent(plugin.name)}/config`, {
        method: "PUT",
        body,
        token,
      });
      setSaveStatus("Saved.");
      setTimeout(() => setSaveStatus(""), 2000);
    } catch (e) {
      setSaveStatus(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section className="mb-4 rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <h2 className="mb-3 text-base font-semibold capitalize text-gray-900 dark:text-gray-100">
        {plugin.name}
      </h2>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        {plugin.schema.map((field) => (
          <div key={field.key}>
            <label className="mb-1 block text-sm font-medium capitalize text-gray-700 dark:text-gray-300">
              {field.key}
            </label>
            <FieldInput
              field={field}
              value={plugin.values[field.key]}
              onChange={(v) => setDraft((d) => ({ ...d, [field.key]: v }))}
            />
            {field.description && (
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {field.description}
              </p>
            )}
          </div>
        ))}
        <div className="flex items-center gap-3">
          <button
            type="submit"
            className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Save
          </button>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {saveStatus}
          </span>
        </div>
      </form>
    </section>
  );
}

export function PluginConfigPage() {
  const { token, isAuthenticated } = useAuth();
  const [plugins, setPlugins] = useState<PluginEntry[] | null>(null);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  const loadPlugins = useCallback(async () => {
    if (!token) return;
    setStatusMsg("Loading plugins…");
    try {
      const list = await apiFetch<PluginListResponse>(
        "/v1/plugins?limit=500",
        { token },
      );
      const found: PluginEntry[] = [];
      for (const { name } of list.plugins) {
        try {
          const cfg = await apiFetch<PluginConfigResponse>(
            `/v1/plugins/${encodeURIComponent(name)}/config`,
            { token },
          );
          if (!cfg.configurable) continue;
          found.push({ name, schema: cfg.schema, values: cfg.values });
        } catch {
          // not running, or 401 -- skip quietly, same as the old page
        }
      }
      setPlugins(found);
      setStatusMsg("");
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e), true);
    }
  }, [token, setStatusMsg]);

  useEffect(() => {
    if (isAuthenticated) loadPlugins();
  }, [isAuthenticated, loadPlugins]);

  return (
    <>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
        Plugin Configuration
      </h1>
      <p className="mb-4 mt-1 text-sm text-gray-600 dark:text-gray-400">
        Edit settings for plugins that expose a config schema — for example a
        news feed's RSS URLs, or a weather plugin's tracked locations.
        Changes apply immediately, live, with no service restart needed.
      </p>
      <LoginPanel onStatus={setStatusMsg} />
      <div
        className={`mb-4 min-h-5 text-sm ${isError ? "text-red-600" : "text-gray-500 dark:text-gray-400"}`}
      >
        {status}
      </div>
      <div>
        {!isAuthenticated && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Log in above to view plugin configuration.
          </p>
        )}
        {isAuthenticated && plugins !== null && plugins.length === 0 && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No configurable plugins found — plugins only appear here once
            they expose a config schema (most first-party plugins do).
          </p>
        )}
        {plugins?.map((p) => (
          <PluginCard key={p.name} plugin={p} token={token} />
        ))}
      </div>
    </>
  );
}
