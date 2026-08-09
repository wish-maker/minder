import { useCallback, useEffect, useState } from "react";

import { InfoCallout } from "../components/InfoCallout";
import { LoginPanel } from "../components/LoginPanel";
import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";

type ModelType = "local" | "remote";
type ModelStatusValue = "ready" | "loading" | "error";

interface ModelInfo {
  id: string;
  name: string;
  type: ModelType;
  provider: string;
  size: string;
  status: ModelStatusValue;
}

interface ModelDetail {
  id: string;
  details: Record<string, unknown>;
  capabilities: string[];
  status: string;
}

interface PullResponse {
  message: string;
  model: string;
  status: "already_exists" | "pulled";
}

interface TestResponse {
  model: string;
  prompt: string;
  response: string;
  status: string;
}

const inputClass =
  "w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-400 focus:outline-none dark:border-gray-600 dark:bg-gray-800";
const primaryButtonClass =
  "rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50";
const secondaryButtonClass =
  "rounded-md border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:hover:bg-gray-800";
const dangerButtonClass =
  "rounded-md border border-red-200 px-3 py-1 text-sm text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-900 dark:hover:bg-red-950";
const statusClass = (isError: boolean) =>
  `mb-4 min-h-5 text-sm ${isError ? "text-red-600" : "text-gray-500 dark:text-gray-400"}`;
const badgeClass =
  "inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-300";

function statusBadgeColor(status: ModelStatusValue): string {
  if (status === "ready") return "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300";
  if (status === "error") return "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300";
  return "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300";
}

function ModelDetailPanel({ modelId }: { modelId: string }) {
  const [loaded, setLoaded] = useState(false);
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [status, setStatus] = useState("");

  async function handleToggle(e: React.SyntheticEvent<HTMLDetailsElement>) {
    if (!e.currentTarget.open || loaded) return;
    setStatus("Loading…");
    try {
      const res = await apiFetch<ModelDetail>(`/v1/models/${encodeURIComponent(modelId)}`);
      setDetail(res);
      setLoaded(true);
      setStatus("");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <details className="mt-2" onToggle={handleToggle}>
      <summary className="cursor-pointer text-xs font-medium text-indigo-600 dark:text-indigo-400">
        Details &amp; capabilities
      </summary>
      <div className="mt-2 text-xs text-gray-600 dark:text-gray-400">
        {status && <p>{status}</p>}
        {detail && (
          <>
            {detail.capabilities.length > 0 && (
              <p className="mb-1">
                <strong>Capabilities:</strong> {detail.capabilities.join(", ")}
              </p>
            )}
            <pre className="max-h-48 overflow-auto rounded bg-gray-50 p-2 dark:bg-gray-800">
              {JSON.stringify(detail.details, null, 2)}
            </pre>
          </>
        )}
      </div>
    </details>
  );
}

function TestPromptWidget({ modelId, token }: { modelId: string; token: string }) {
  const [prompt, setPrompt] = useState("Hello, test.");
  const [result, setResult] = useState<TestResponse | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleTest() {
    setBusy(true);
    setStatus("Running…");
    setResult(null);
    try {
      const res = await apiFetch<TestResponse>(
        `/v1/models/${encodeURIComponent(modelId)}/test`,
        { method: "POST", body: { prompt }, token },
      );
      setResult(res);
      setStatus("");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  return (
    <div className="mt-2 border-t border-gray-100 pt-2 dark:border-gray-800">
      <div className="flex gap-2">
        <input
          className={inputClass}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <button
          onClick={handleTest}
          disabled={!token || busy}
          className={secondaryButtonClass}
        >
          Test
        </button>
      </div>
      {status && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{status}</p>}
      {result && (
        <p className="mt-2 whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs dark:bg-gray-800">
          {result.response}
        </p>
      )}
    </div>
  );
}

function ModelCard({
  model,
  token,
  onDeleted,
}: {
  model: ModelInfo;
  token: string;
  onDeleted: (id: string) => void;
}) {
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleDelete() {
    if (!confirm(`Delete model "${model.name}"? This removes it from Ollama.`)) return;
    setBusy(true);
    setStatus("Deleting…");
    try {
      await apiFetch(`/v1/models/${encodeURIComponent(model.id)}`, {
        method: "DELETE",
        token,
      });
      onDeleted(model.id);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  return (
    <section className="mb-4 rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-gray-900 dark:text-gray-100">
            🤖 {model.name}
            <span className={`${badgeClass} ${statusBadgeColor(model.status)}`}>
              {model.status}
            </span>
          </h2>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {model.type} · {model.provider} · {model.size}
          </p>
          <ModelDetailPanel modelId={model.id} />
          <TestPromptWidget modelId={model.id} token={token} />
        </div>
        <button
          onClick={handleDelete}
          disabled={!token || busy}
          className={dangerButtonClass}
        >
          🗑 Delete
        </button>
      </div>
      {status && <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{status}</p>}
    </section>
  );
}

function PullModelForm({
  token,
  onPulled,
}: {
  token: string;
  onPulled: () => void;
}) {
  const [modelId, setModelId] = useState("");
  const [status, setStatus] = useState("");
  const [pulling, setPulling] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!modelId.trim()) {
      setStatus("Model id is required.");
      return;
    }
    setPulling(true);
    setStatus("Pulling… this blocks until the download finishes — can take several minutes for large models. Don't navigate away.");
    try {
      const res = await apiFetch<PullResponse>("/v1/models", {
        method: "POST",
        body: { model_id: modelId },
        token,
      });
      setStatus(
        res.status === "already_exists"
          ? `"${res.model}" is already pulled.`
          : `Pulled "${res.model}".`,
      );
      setModelId("");
      onPulled();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
    setPulling(false);
  }

  return (
    <section className="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <h2 className="mb-1 text-base font-semibold text-gray-900 dark:text-gray-100">
        ⬇️ Pull a model
      </h2>
      <form onSubmit={handleSubmit} className="mt-2 flex gap-2">
        <input
          className={inputClass}
          placeholder="e.g. llama3.2:latest"
          value={modelId}
          onChange={(e) => setModelId(e.target.value)}
          disabled={pulling}
        />
        <button
          type="submit"
          disabled={!token || pulling}
          className={primaryButtonClass}
        >
          {pulling ? "Pulling…" : "Pull"}
        </button>
      </form>
      {!token && (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Log in to pull a model.
        </p>
      )}
      <p className={statusClass(false)}>{status}</p>
    </section>
  );
}

export function ModelManagementPage() {
  const { token } = useAuth();
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  const loadModels = useCallback(async () => {
    setStatusMsg("Loading…");
    try {
      const res = await apiFetch<ModelInfo[]>("/v1/models");
      setModels(res);
      setStatusMsg("");
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e), true);
    }
  }, [setStatusMsg]);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  return (
    <>
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Pull, delete, and test Ollama models on Minder's own model-management
        service. Browsing is open for everyone; log in to pull, delete, or
        test a prompt.
      </p>
      <InfoCallout icon="🤖">
        <a className="font-medium underline" href="http://localhost:8080">
          OpenWebUI
        </a>
        's own Admin Panel → Connections → Ollama → Manage offers the same
        pull/delete against this same Ollama instance too, with more
        per-model settings (system prompts, parameters) if you're already
        there for chat.
      </InfoCallout>
      <div className="mt-4">
        <LoginPanel onStatus={setStatusMsg} />
      </div>
      <div className={statusClass(isError)}>{status}</div>
      <PullModelForm token={token} onPulled={loadModels} />
      {models !== null && models.length === 0 && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          No models pulled yet — use the form above.
        </p>
      )}
      {models?.map((m) => (
        <ModelCard
          key={m.id}
          model={m}
          token={token}
          onDeleted={(id) => setModels((prev) => (prev ?? []).filter((mm) => mm.id !== id))}
        />
      ))}
    </>
  );
}
