import { useEffect, useState } from "react";

import { useConfirm } from "../components/ConfirmDialog";
import { InfoCallout } from "../components/InfoCallout";
import { PageHeader } from "../components/PageHeader";
import { StatusLine } from "../components/StatusLine";
import { EmptyState } from "../components/EmptyState";
import { apiFetch, friendlyErrorMessage } from "../lib/api";
import type { Paginated } from "../lib/api";
import { filterByText } from "../lib/filterByText";
import { useAsyncResource } from "../lib/useAsyncResource";
import { useAuth } from "../lib/auth";
import { openWebUiUrl } from "../lib/links";
import { formatElapsed, useElapsedSeconds } from "../lib/useElapsedSeconds";
import {
  badgeClass,
  badgeTone,
  cardClass,
  destructiveButtonClass,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "../lib/ui";

type ModelType = "local" | "remote";
type ModelStatusValue = "ready" | "loading" | "error";

export interface ModelInfo {
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

function statusBadgeColor(status: ModelStatusValue): string {
  if (status === "ready") return badgeTone.success;
  if (status === "error") return badgeTone.danger;
  return badgeTone.warn;
}

function ModelDetailPanel({ modelId }: { modelId: string }) {
  // Capabilities load eagerly (on mount) and render directly in the card --
  // found live: they were hidden behind the same "Details & capabilities"
  // toggle as the raw Ollama JSON dump, so seeing what a model can even DO
  // required opening a wall of JSON first. Only the JSON itself stays
  // collapsed (it's genuinely long and rarely needed).
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [status, setStatus] = useState("Loading…");

  useEffect(() => {
    let cancelled = false;
    apiFetch<ModelDetail>(`/v1/models/${encodeURIComponent(modelId)}`)
      .then((res) => {
        if (!cancelled) {
          setDetail(res);
          setStatus("");
        }
      })
      .catch((e) => {
        if (!cancelled) setStatus(friendlyErrorMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [modelId]);

  return (
    <div className="mt-1 text-xs text-gray-600 dark:text-gray-400">
      {status && <p>{status}</p>}
      {detail && detail.capabilities.length > 0 && (
        <p>
          <strong>Capabilities:</strong> {detail.capabilities.join(", ")}
        </p>
      )}
      {detail && (
        <details className="mt-1">
          <summary className="cursor-pointer text-xs font-medium text-indigo-600 dark:text-indigo-400">
            Full details (JSON)
          </summary>
          <pre className="mt-2 max-h-48 overflow-auto rounded bg-gray-50 p-2 dark:bg-gray-800">
            {JSON.stringify(detail.details, null, 2)}
          </pre>
        </details>
      )}
    </div>
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
      setStatus(friendlyErrorMessage(e));
    }
    setBusy(false);
  }

  return (
    <div className="mt-2 border-t border-gray-100 pt-2 dark:border-gray-800">
      <div className="flex gap-2">
        <input
          className={inputClass}
          aria-label="Test prompt"
          placeholder="Ask the model something…"
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

export function ModelCard({
  model,
  token,
  isAdmin,
  onDeleted,
  confirm,
}: {
  model: ModelInfo;
  token: string;
  isAdmin: boolean;
  onDeleted: (id: string) => void;
  confirm: ReturnType<typeof useConfirm>["confirm"];
}) {
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleDelete() {
    const ok = await confirm({
      title: "Delete model?",
      message: `This removes "${model.name}" (${model.size}) from Ollama. You'll need to pull it again to use it.`,
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    setStatus("Deleting…");
    try {
      await apiFetch(`/v1/models/${encodeURIComponent(model.id)}`, {
        method: "DELETE",
        token,
      });
      onDeleted(model.id);
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
    setBusy(false);
  }

  return (
    <section className={`mb-4 ${cardClass}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-gray-900 dark:text-gray-100">
            <span aria-hidden="true">🤖</span> {model.name}
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
          disabled={!isAdmin || busy}
          title={
            !isAdmin
              ? token
                ? "Admin role required"
                : "Log in as an admin to delete models"
              : undefined
          }
          className={destructiveButtonClass}
        >
          🗑 Delete
        </button>
      </div>
      {status && <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{status}</p>}
    </section>
  );
}


export function PullModelForm({
  token,
  isAdmin,
  onPulled,
}: {
  token: string;
  isAdmin: boolean;
  onPulled: () => void;
}) {
  const [modelId, setModelId] = useState("");
  const [status, setStatus] = useState("");
  const [pulling, setPulling] = useState(false);
  const elapsed = useElapsedSeconds(pulling);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!modelId.trim()) {
      setStatus("Model id is required.");
      return;
    }
    setPulling(true);
    setStatus("");
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
      setStatus(friendlyErrorMessage(e));
    }
    setPulling(false);
  }

  return (
    <section className={`mb-6 ${cardClass}`}>
      <h2 className="mb-1 text-base font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">⬇️</span> Pull a model
      </h2>
      <fieldset disabled={!isAdmin}>
        <form onSubmit={handleSubmit} className="mt-2 flex gap-2">
          <input
            className={inputClass}
            aria-label="Model id to pull"
            placeholder="e.g. llama3.2:latest"
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            disabled={pulling}
          />
          <button type="submit" disabled={pulling} className={primaryButtonClass}>
            {pulling ? "Pulling…" : "Pull"}
          </button>
        </form>
      </fieldset>
      {!isAdmin && (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {token ? "Admin role required to pull a model." : "Log in as an admin to pull a model."}
        </p>
      )}
      {pulling && (
        <StatusLine>
          <span className="inline-block animate-spin">⏳</span> Pulling —{" "}
          {formatElapsed(elapsed)} elapsed. This blocks until the download
          finishes (can take several minutes for large models) — don't
          navigate away.
        </StatusLine>
      )}
      {!pulling && <StatusLine>{status}</StatusLine>}
    </section>
  );
}

export function ModelManagementPage() {
  const { token, role } = useAuth();
  const isAdmin = role === "admin";
  const { confirm, dialog } = useConfirm();
  // Single list read → useAsyncResource (cancels on unmount, stale-guard). Pull
  // and delete refresh via reload() rather than local optimistic edits, so the
  // list (and each model's derived size/status) always reflects Ollama. #502
  const modelsRes = useAsyncResource((signal) =>
    // `?? []`: a response omitting `items` would otherwise resolve `data` to
    // `undefined`, past the `models !== null` guards below and crashing on
    // `.length`/`.map` -- same failure shape as HealthStrip.tsx's `services`.
    apiFetch<Paginated<ModelInfo>>("/v1/models?limit=500", { signal }).then(
      (r) => r.items ?? [],
    ),
  );
  const models = modelsRes.data;
  const [filter, setFilter] = useState("");

  const needle = filter.trim().toLowerCase();
  const visibleModels = filterByText(models ?? [], filter, (m) => [
    m.name,
    m.provider,
    m.type,
  ]);

  return (
    <>
      {dialog}
      <PageHeader icon="🤖" title="Model Management" />
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Pull, delete, and test Ollama models on Minder's own model-management
        service. Browsing is open for everyone; log in to test a prompt.
        Pulling and deleting require an admin account.
      </p>
      <InfoCallout icon="🤖">
        <a className="font-medium underline" href={openWebUiUrl}>
          OpenWebUI
        </a>
        's own Admin Panel → Connections → Ollama → Manage offers the same
        pull/delete against this same Ollama instance too, with more
        per-model settings (system prompts, parameters) if you're already
        there for chat.
      </InfoCallout>
      <StatusLine isError={!!modelsRes.error}>
        {modelsRes.error ?? (modelsRes.loading ? "Loading…" : "")}
      </StatusLine>
      <PullModelForm token={token} isAdmin={isAdmin} onPulled={modelsRes.reload} />
      {models !== null && models.length === 0 && (
        <EmptyState>No models pulled yet — use the form above.</EmptyState>
      )}
      {models !== null && models.length > 0 && (
        <div className="mb-3 flex items-center gap-3">
          <input
            className={`${inputClass} max-w-xs`}
            type="text"
            aria-label="Filter models"
            placeholder="Filter by name, provider, or type…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          {needle && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {visibleModels?.length ?? 0} of {models.length}
            </span>
          )}
        </div>
      )}
      {needle && visibleModels?.length === 0 && (
        <EmptyState>No pulled models match "{filter}".</EmptyState>
      )}
      {visibleModels?.map((m) => (
        <ModelCard
          key={m.id}
          model={m}
          token={token}
          isAdmin={isAdmin}
          onDeleted={modelsRes.reload}
          confirm={confirm}
        />
      ))}
    </>
  );
}
