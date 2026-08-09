import { useCallback, useEffect, useState } from "react";

import { LoginPanel } from "../components/LoginPanel";
import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";

interface ModelInfo {
  id: string;
  name: string;
  type: string;
  provider: string;
  size: string;
  status: string;
}

interface PullResponse {
  message: string;
}

interface TestResponse {
  response: string;
}

function ModelCard({
  model,
  token,
  onDeleted,
  onStatus,
}: {
  model: ModelInfo;
  token: string;
  onDeleted: () => void;
  onStatus: (msg: string, isError?: boolean) => void;
}) {
  const [prompt, setPrompt] = useState("Hello, test.");
  const [testResult, setTestResult] = useState("");

  async function handleTest() {
    if (!token) {
      onStatus("Log in first.", true);
      return;
    }
    setTestResult("Testing…");
    try {
      const data = await apiFetch<TestResponse>(
        `/v1/models/${encodeURIComponent(model.id)}/test`,
        { method: "POST", body: { prompt }, token },
      );
      setTestResult(data.response || "(empty response)");
    } catch (e) {
      setTestResult("Error: " + (e instanceof Error ? e.message : String(e)));
    }
  }

  async function handleDelete() {
    if (!token) {
      onStatus("Log in first.", true);
      return;
    }
    if (!window.confirm(`Delete model "${model.id}"? This cannot be undone.`)) {
      return;
    }
    try {
      await apiFetch(`/v1/models/${encodeURIComponent(model.id)}`, {
        method: "DELETE",
        token,
      });
      onDeleted();
    } catch (e) {
      onStatus(e instanceof Error ? e.message : String(e), true);
    }
  }

  return (
    <section className="model-card">
      <div className="row">
        <h2>{model.name}</h2>
        <span className="meta">{model.size}</span>
      </div>
      <div className="meta">status: {model.status}</div>
      <div className="actions">
        <input
          type="text"
          className="test-prompt"
          placeholder="test prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <button type="button" onClick={handleTest}>
          Test
        </button>
        <button type="button" className="danger" onClick={handleDelete}>
          Delete
        </button>
      </div>
      <div className="test-result">{testResult}</div>
    </section>
  );
}

export function ModelManagementPage() {
  const { token } = useAuth();
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);
  const [pullModelId, setPullModelId] = useState("");
  const [pullStatus, setPullStatus] = useState("");

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  const loadModels = useCallback(async () => {
    setStatusMsg("Loading models…");
    try {
      const list = await apiFetch<ModelInfo[]>("/v1/models");
      setModels(list);
      setStatusMsg("");
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e), true);
    }
  }, [setStatusMsg]);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  async function handlePull() {
    const modelId = pullModelId.trim();
    if (!modelId) return;
    if (!token) {
      setStatusMsg("Log in first.", true);
      return;
    }
    setPullStatus("Pulling… this can take a while, please wait.");
    try {
      const data = await apiFetch<PullResponse>("/v1/models", {
        method: "POST",
        body: { model_id: modelId },
        token,
      });
      setPullStatus(data.message || "Pulled.");
      setPullModelId("");
      loadModels();
    } catch (e) {
      setPullStatus(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <>
      <h1>Model Management</h1>
      <p className="hint">
        List, pull, delete, and test-prompt local Ollama models. Listing
        works without logging in; pulling/deleting/testing needs a JWT (same
        login as Plugin Configuration).
      </p>
      <LoginPanel onStatus={setStatusMsg} />
      <div className={`status${isError ? " error" : ""}`}>{status}</div>

      <div className="pull-form">
        <h2>Pull a model</h2>
        <p className="hint">
          Downloads from the Ollama library — can take a while and use
          several GB, depending on the model. Requires login.
        </p>
        <input
          type="text"
          placeholder="e.g. llama3.2:1b"
          value={pullModelId}
          onChange={(e) => setPullModelId(e.target.value)}
        />
        <button type="button" onClick={handlePull}>
          Pull
        </button>
        <span className="save-status">{pullStatus}</span>
      </div>

      <h2>Installed models</h2>
      <div>
        {models !== null && models.length === 0 && (
          <p>No models installed yet — pull one above.</p>
        )}
        {models?.map((m) => (
          <ModelCard
            key={m.id}
            model={m}
            token={token}
            onDeleted={loadModels}
            onStatus={setStatusMsg}
          />
        ))}
      </div>
    </>
  );
}
