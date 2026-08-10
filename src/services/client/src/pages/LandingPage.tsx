import { Link } from "react-router-dom";

import { InfoCallout } from "../components/InfoCallout";
import { useAuth } from "../lib/auth";
import { openWebUiUrl } from "../lib/links";
import { cardClass } from "../lib/ui";

interface ToolCardProps {
  to: string;
  icon: string;
  title: string;
  children: string;
  /** Shows a "Step N" badge -- used on the RAG section to signal the
   * intended first-time order (knowledge base before pipeline before
   * querying), since the three cards otherwise carry identical visual
   * weight and give a first-time user no sense of where to start. */
  step?: number;
}

function ToolCard({ to, icon, title, children, step }: ToolCardProps) {
  return (
    <Link
      to={to}
      className={`flex flex-col gap-2 ${cardClass} transition hover:border-indigo-300 hover:shadow-md`}
    >
      <div className="flex items-center gap-2">
        <span className="text-2xl" aria-hidden="true">
          {icon}
        </span>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          {title}
        </h3>
        {step && (
          <span className="ml-auto flex-shrink-0 rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300">
            Step {step}
          </span>
        )}
      </div>
      <p className="text-sm leading-relaxed text-gray-600 dark:text-gray-400">
        {children}
      </p>
    </Link>
  );
}

function ToolSection({
  icon,
  title,
  subtitle,
  children,
}: {
  icon: string;
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-6">
      <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
        {icon} {title}
      </h2>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">{children}</div>
    </section>
  );
}

export function LandingPage() {
  const { isAuthenticated, username } = useAuth();

  return (
    <>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
        Minder
      </h1>
      <p className="mb-2 text-sm text-gray-600 dark:text-gray-400">
        {isAuthenticated
          ? `Logged in as ${username}.`
          : "Browsing is open for everyone; log in on any page below to make changes."}
      </p>
      <p className="mb-6 text-sm text-gray-600 dark:text-gray-400">
        New here? Start with{" "}
        <Link to="/rag" className="underline hover:text-indigo-600 dark:hover:text-indigo-400">
          Knowledge Bases
        </Link>{" "}
        — steps 1–2 below take you from uploading a document to asking a
        question over it. Knowledge Graph is a separate, optional path over
        the same documents, not a required step 3.
      </p>

      <ToolSection
        icon="🔎"
        title="RAG"
        subtitle="Store documents, then ask questions over them — vector search or knowledge-graph, your choice."
      >
        <ToolCard to="/rag" icon="📚" title="Knowledge Bases" step={1}>
          Create knowledge bases and upload documents (PDF/TXT/MD) for
          Minder's own RAG pipeline — the data your RAG Pipelines search
          over. Manage documents individually without rebuilding the whole
          knowledge base.
        </ToolCard>
        <ToolCard to="/rag/pipelines" icon="🔎" title="RAG Pipelines" step={2}>
          Combine your knowledge bases into a pipeline, then ask it
          questions — the default settings work fine to start. Advanced
          options (HyDE/Self-RAG/corrective retrieval, reranking,
          compression, hybrid search) are there to tune result quality once
          you know what you're optimizing for.
        </ToolCard>
        <ToolCard to="/rag/graph" icon="🧬" title="Knowledge Graph">
          Extract entities and relationships from text with spaCy, build them
          into a Neo4j knowledge graph, then explore who's connected to whom
          — a different, optional retrieval paradigm from vector search, not
          a required next step after Pipelines.
        </ToolCard>
      </ToolSection>

      <ToolSection
        icon="🛒"
        title="Marketplace"
        subtitle="Everything you can turn on for this installation — six first-party plugins and the feature bundles they belong to."
      >
        <ToolCard to="/marketplace/plugins/available" icon="🔍" title="Available Plugins">
          Browse and install Minder plugins — see what's available, check
          dependencies and conflicts against what you've already installed,
          and turn plugins on without leaving the browser.
        </ToolCard>
        <ToolCard to="/marketplace/plugins/installed" icon="🧩" title="Installed Plugins">
          Manage what you've installed — enable, disable, uninstall, or edit
          a plugin's settings (news feed URLs, weather locations, and similar
          per-plugin options), all from the same place.
        </ToolCard>
        <ToolCard to="/marketplace/plugins/ai-tools" icon="🧰" title="AI Tools">
          See every function-calling tool Minder's plugins expose — what's
          live right now from running plugins, and the durable catalog
          Marketplace keeps with tier info.
        </ToolCard>
        <ToolCard to="/marketplace/bundles" icon="📦" title="Bundle Management">
          Turn optional feature bundles (inference, RAG, chat, monitoring,
          voice, graph-rag) on or off, see which services each one claims,
          and reconcile the running stack to match.
        </ToolCard>
      </ToolSection>

      <ToolSection
        icon="⚙️"
        title="Platform"
        subtitle="Models, health, and voice — the operator surface plus a couple of capabilities you can also just use directly."
      >
        <ToolCard to="/platform" icon="🤖" title="Model Management">
          Pull, delete, and test Ollama models directly against Minder's
          model-management service — the same Ollama instance the whole
          platform uses.
        </ToolCard>
        <ToolCard to="/platform/status" icon="🩺" title="Status">
          Health, reported version, and recent logs for every core service —
          one place to check what's up, what's degraded, and why.
        </ToolCard>
        <ToolCard to="/platform/voice" icon="🎙️" title="Voice">
          Text-to-speech (Piper offline, gTTS fallback) and speech-to-text —
          type or record, hear or read the result, ~12 languages supported.
        </ToolCard>
      </ToolSection>

      <div className="flex flex-col gap-3">
        <InfoCallout icon="🤖">
          <a className="font-medium underline" href={openWebUiUrl}>
            OpenWebUI
          </a>
          's own Admin Panel → Connections → Ollama → Manage offers the same
          pull/delete against this same Ollama instance too, with more
          per-model settings (system prompts, parameters) if you're already
          there for chat.
        </InfoCallout>
        <InfoCallout icon="⚠️">
          OpenWebUI's own "Knowledge" feature is a separate, disconnected
          system — it has no access to Minder's actual RAG pipeline
          (knowledge bases, chunking, or the HyDE/Self-RAG/corrective
          retrieval methods above). Use Knowledge Bases and RAG Pipelines
          above for the real thing.
        </InfoCallout>
      </div>
    </>
  );
}
