import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { HealthStrip } from "../components/HealthStrip";
import { InfoCallout } from "../components/InfoCallout";
import { Skeleton } from "../components/Skeleton";
import { apiFetch, type Paginated } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { BundlesResponse } from "../lib/bundles";
import { openWebUiUrl } from "../lib/links";
import { cardClass } from "../lib/ui";
import { useAsyncResource } from "../lib/useAsyncResource";

interface HomeStats {
  kbCount: number;
  pipelineCount: number;
  bundlesEnabled: number;
  bundlesTotal: number;
  modelCount: number;
}

interface StatCardProps {
  to: string;
  icon: string;
  label: string;
  value: number | string | null;
  loading: boolean;
}

function StatCard({ to, icon, label, value, loading }: StatCardProps) {
  return (
    <Link
      to={to}
      className={`flex flex-col gap-1 ${cardClass} transition hover:border-indigo-300 hover:shadow-md`}
    >
      <span className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        <span aria-hidden="true">{icon}</span> {label}
      </span>
      {loading && value === null ? (
        <Skeleton className="h-8 w-12" />
      ) : (
        <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          {value ?? "—"}
        </span>
      )}
    </Link>
  );
}

interface PrimaryAction {
  to: string;
  icon: string;
  title: string;
  body: string;
}

/** The single most useful next step, derived from what's actually in this
 * installation -- a first-time user with 0 knowledge bases and someone who
 * already has 12 pipelines running shouldn't see the same call to action. */
function primaryAction(stats: HomeStats | null): PrimaryAction {
  if (stats === null || stats.kbCount === 0) {
    return {
      to: "/rag",
      icon: "📚",
      title: "Create your first knowledge base",
      body: "Upload a document (PDF/TXT/MD) to start — every other RAG feature builds on this.",
    };
  }
  if (stats.pipelineCount === 0) {
    return {
      to: "/rag/pipelines",
      icon: "🔎",
      title: "Build a pipeline",
      body: `You have ${stats.kbCount} knowledge base${stats.kbCount === 1 ? "" : "s"} ready — combine them into a pipeline to start asking questions.`,
    };
  }
  return {
    to: "/rag/pipelines",
    icon: "💬",
    title: "Ask a question",
    body: `Jump back into your ${stats.pipelineCount} pipeline${stats.pipelineCount === 1 ? "" : "s"} to query your knowledge bases.`,
  };
}

function PrimaryActionCard({ stats, loading }: { stats: HomeStats | null; loading: boolean }) {
  const action = primaryAction(stats);
  return (
    <Link
      to={action.to}
      className={`mb-6 flex items-center gap-4 ${cardClass} border-indigo-200 transition hover:border-indigo-400 hover:shadow-md dark:border-indigo-900`}
    >
      <span className="text-3xl" aria-hidden="true">
        {action.icon}
      </span>
      <div className="flex-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
          {loading && stats === null ? <Skeleton className="h-5 w-48" /> : action.title}
        </h2>
        <p className="mt-0.5 text-sm text-gray-600 dark:text-gray-400">
          {loading && stats === null ? <Skeleton className="mt-1 h-4 w-72" /> : action.body}
        </p>
      </div>
      <span className="text-indigo-600 dark:text-indigo-400" aria-hidden="true">
        →
      </span>
    </Link>
  );
}

interface ExploreLink {
  to: string;
  icon: string;
  label: string;
}

const EXPLORE_LINKS: ExploreLink[] = [
  { to: "/plugins/available", icon: "🧩", label: "Plugins" },
  { to: "/ai-tools/available", icon: "🧰", label: "AI Tools" },
  { to: "/bundles/available", icon: "📦", label: "Bundles" },
  { to: "/rag/graph", icon: "🧬", label: "Knowledge Graph" },
  { to: "/platform/voice", icon: "🎙️", label: "Voice" },
  { to: "/platform/status", icon: "🩺", label: "Status" },
];

function ExploreSection() {
  return (
    <section className="mb-6">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
        More to explore
      </h2>
      <div className="flex flex-wrap gap-2">
        {EXPLORE_LINKS.map((l) => (
          <Link
            key={l.to}
            to={l.to}
            className="flex items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 transition hover:border-indigo-300 hover:text-indigo-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:border-indigo-700 dark:hover:text-indigo-300"
          >
            <span aria-hidden="true">{l.icon}</span> {l.label}
          </Link>
        ))}
      </div>
    </section>
  );
}

function Callouts(): ReactNode {
  return (
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
        system — it has no access to Minder's actual RAG pipeline (knowledge
        bases, chunking, or the HyDE/Self-RAG/corrective retrieval methods
        above). Use Knowledge Bases and RAG Pipelines for the real thing.
      </InfoCallout>
    </div>
  );
}

/** Task-first home dashboard (replacing the old static sitemap-as-cards
 * LandingPage): what's actually going on in this installation right now
 * (health, counts) and the one next step most worth taking, with full
 * navigation demoted to a compact "More to explore" strip since the sidebar
 * already covers that job. */
export function HomePage() {
  const { isAuthenticated, username } = useAuth();
  const stats = useAsyncResource<HomeStats>((signal) =>
    Promise.all([
      apiFetch<Paginated<unknown>>("/v1/rag/knowledge-bases?limit=1", { signal }),
      apiFetch<Paginated<unknown>>("/v1/rag/pipeline?limit=1", { signal }),
      apiFetch<BundlesResponse>("/v1/bundles", { signal }),
      apiFetch<Paginated<unknown>>("/v1/models?limit=1", { signal }),
    ]).then(([kbs, pipelines, bundles, models]) => ({
      kbCount: kbs.total,
      pipelineCount: pipelines.total,
      bundlesEnabled: bundles.bundles.filter((b) => b.enabled).length,
      bundlesTotal: bundles.count,
      modelCount: models.total,
    })),
  );

  return (
    <>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
        {isAuthenticated ? `Welcome back, ${username}` : "Minder"}
      </h1>
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        {isAuthenticated
          ? "Here's what's running right now."
          : "Browsing is open for everyone — log in on any page to make changes."}
      </p>

      <HealthStrip />
      <PrimaryActionCard stats={stats.data} loading={stats.loading} />

      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          to="/rag"
          icon="📚"
          label="Knowledge Bases"
          value={stats.data?.kbCount ?? null}
          loading={stats.loading}
        />
        <StatCard
          to="/rag/pipelines"
          icon="🔎"
          label="Pipelines"
          value={stats.data?.pipelineCount ?? null}
          loading={stats.loading}
        />
        <StatCard
          to="/bundles/installed"
          icon="📦"
          label="Bundles Enabled"
          value={stats.data ? `${stats.data.bundlesEnabled}/${stats.data.bundlesTotal}` : null}
          loading={stats.loading}
        />
        <StatCard
          to="/platform"
          icon="🤖"
          label="Models"
          value={stats.data?.modelCount ?? null}
          loading={stats.loading}
        />
      </div>

      <ExploreSection />
      <Callouts />
    </>
  );
}
