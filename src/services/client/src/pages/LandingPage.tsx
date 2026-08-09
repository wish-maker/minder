import { Link } from "react-router-dom";

import { useAuth } from "../lib/auth";

export function LandingPage() {
  const { isAuthenticated, username } = useAuth();

  return (
    <>
      <h1>Minder</h1>
      <p className="hint">
        {isAuthenticated
          ? `Logged in as ${username}.`
          : "Log in below to make changes; browsing is open."}
      </p>
      <ul>
        <li>
          <Link to="/plugin-config">Plugin Configuration</Link> — edit news
          feeds, weather locations, and other plugin settings.
        </li>
        <li>
          <Link to="/knowledge-bases">Knowledge Bases</Link> — create
          knowledge bases and upload documents for Minder's own RAG pipeline.
        </li>
        <li>
          <Link to="/rag-pipelines">RAG Pipelines</Link> — build a pipeline
          over your knowledge bases and query it.
        </li>
      </ul>
      <p className="hint">
        Looking to pull, delete, or manage local Ollama models? Use{" "}
        <a href="http://localhost:8080">OpenWebUI</a>'s own Admin Panel →
        Connections → Ollama → Manage — same Ollama instance, more complete
        (system prompts, per-model parameters), and integrated with the chat
        you'd actually use the model in.
      </p>
      <p className="hint">
        OpenWebUI's own "Knowledge" feature is a separate, disconnected system
        — it has no access to Minder's actual RAG pipeline (knowledge bases,
        chunking, or the HyDE/Self-RAG/corrective retrieval methods below).
        Use Knowledge Bases and RAG Pipelines above for the real thing.
      </p>
    </>
  );
}
