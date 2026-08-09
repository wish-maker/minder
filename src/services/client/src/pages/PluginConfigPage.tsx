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
        type="checkbox"
        checked={!!value}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }
  if (inputType === "password") {
    return (
      <input
        type="password"
        placeholder="unchanged (leave blank to keep current value)"
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  if (inputType === "number") {
    return (
      <input
        type="number"
        step={field.type === "float" ? "any" : undefined}
        defaultValue={value as number | string}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <input
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
    <section className="plugin-card">
      <h2>{plugin.name}</h2>
      <form onSubmit={handleSubmit}>
        {plugin.schema.map((field) => (
          <div className="field" key={field.key}>
            <label>{field.key}</label>
            <FieldInput
              field={field}
              value={plugin.values[field.key]}
              onChange={(v) => setDraft((d) => ({ ...d, [field.key]: v }))}
            />
            {field.description && <p className="hint">{field.description}</p>}
          </div>
        ))}
        <button type="submit">Save</button>
        <span className="save-status">{saveStatus}</span>
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
      <h1>Plugin Configuration</h1>
      <p className="hint">
        Edit settings for plugins that expose a config schema (e.g. news
        feeds, weather locations). Changes apply immediately, no restart
        needed.
      </p>
      <LoginPanel onStatus={setStatusMsg} />
      <div className={`status${isError ? " error" : ""}`}>{status}</div>
      <div>
        {!isAuthenticated && <p>Log in to view plugin configuration.</p>}
        {isAuthenticated && plugins !== null && plugins.length === 0 && (
          <p>No configurable plugins found.</p>
        )}
        {plugins?.map((p) => (
          <PluginCard key={p.name} plugin={p} token={token} />
        ))}
      </div>
    </>
  );
}
